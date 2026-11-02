FROM python:3.12.9-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.lock pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -c requirements.lock . && pip check
RUN useradd --create-home --uid 10001 simulator && mkdir /artifacts && chown simulator /artifacts
COPY configs ./configs

FROM base AS test
RUN pip install --no-cache-dir -c requirements.lock '.[dev]' && pip check
COPY tests ./tests
COPY acceptance ./acceptance
COPY scripts ./scripts
USER simulator
ENV PYTEST_ADDOPTS="-o cache_dir=/tmp/pytest-cache" RUFF_CACHE_DIR=/tmp/ruff-cache COVERAGE_FILE=/tmp/.coverage
ENTRYPOINT ["python", "scripts/check.py"]

FROM base AS runtime
USER simulator
ENTRYPOINT ["rf-test"]
CMD ["run", "--config", "/app/configs/demo.yaml", "--output", "/artifacts"]
