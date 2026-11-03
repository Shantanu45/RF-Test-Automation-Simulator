from typing import Any

from bson import BSON
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from rf_test_sim.errors import StorageError
from rf_test_sim.persistence.artifacts import MAX_DOCUMENT_BYTES, validate_document


class MongoRepository:
    def __init__(self, uri: str, database: str = "rf_sim") -> None:
        try:
            self._client: MongoClient[dict[str, Any]] = MongoClient(
                uri,
                serverSelectionTimeoutMS=3000,
                connectTimeoutMS=3000,
                socketTimeoutMS=5000,
                retryWrites=False,
            )
        except (PyMongoError, ValueError) as error:
            raise StorageError("invalid MongoDB connection configuration") from error
        try:
            self._collection = self._client[database]["runs"]
            self._collection.create_index("run_id", unique=True)
        except (PyMongoError, ValueError) as error:
            self._client.close()
            raise StorageError("MongoDB initialization failed") from error

    def save(self, document: dict[str, Any]) -> None:
        document = validate_document(document)
        if len(BSON.encode(document)) > MAX_DOCUMENT_BYTES:
            raise StorageError("run document exceeds BSON size bound")
        try:
            self._collection.update_one(
                {"run_id": document["run_id"]}, {"$setOnInsert": document}, upsert=True
            )
            if self.load(document["run_id"]) != document:
                raise StorageError("run ID already contains different results")
        except PyMongoError as error:
            raise StorageError(
                "MongoDB save failed; local artifact retained"
            ) from error

    def load(self, run_id: str) -> dict[str, Any]:
        try:
            document = self._collection.find_one({"run_id": run_id}, {"_id": False})
        except PyMongoError as error:
            raise StorageError("MongoDB read failed") from error
        if document is None:
            raise StorageError("run not found")
        return validate_document(document)

    def close(self) -> None:
        self._client.close()
