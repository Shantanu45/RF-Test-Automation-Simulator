import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from pymongo import MongoClient

from rf_test_sim.config import RunConfig
from rf_test_sim.errors import StorageError
from rf_test_sim.persistence.mongodb import MongoRepository
from rf_test_sim.simulation.bench import SimulationBench
from rf_test_sim.workflow import execute

pytestmark = pytest.mark.mongo


@pytest.fixture
def repository() -> Iterator[MongoRepository]:
    uri = os.environ.get("TEST_MONGODB_URI")
    if not uri:
        pytest.skip("set TEST_MONGODB_URI to explicitly enable disposable database tests")
    database = f"rf_sim_test_{uuid4().hex}"
    instance = MongoRepository(uri, database)
    try:
        yield instance
    finally:
        instance.close()
        with MongoClient(uri, serverSelectionTimeoutMS=3000) as client:
            client.drop_database(database)


def test_real_database_roundtrip_and_replay(repository: MongoRepository) -> None:
    document = execute(RunConfig(), SimulationBench).document()
    repository.save(document)
    first = repository.load(document["run_id"])
    repository.save(document)
    assert repository.load(document["run_id"]) == first
    assert first["verdict"] == "PASS"
    assert first["points"][0]["gain_db"] == 20
    document["software_version"] = "conflicting-run"
    with pytest.raises(StorageError, match="different"):
        repository.save(document)
