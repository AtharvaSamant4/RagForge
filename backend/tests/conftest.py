import os
import sys
import tempfile
from pathlib import Path

import pytest

TEST_DIR = tempfile.TemporaryDirectory(prefix="ragforge-tests-")
root = Path(TEST_DIR.name)
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{(root / 'test.db').as_posix()}")
os.environ["STORAGE_DIR"] = str(root / "uploads")
os.environ["EXPORT_DIR"] = str(root / "exports")
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["GENERATION_PROVIDER"] = "extractive"
os.environ["RATE_LIMIT_PER_MINUTE"] = "10000"
os.environ["APP_ORIGINS"] = "http://localhost:3000"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.db import Base, SessionLocal, engine
from app.main import app


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    TEST_DIR.cleanup()


@pytest.fixture(autouse=True)
def database():
    if engine.dialect.name == "postgresql":
        from sqlalchemy import text
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    yield


@pytest.fixture
def client():
    with TestClient(app, headers={"origin": "http://localhost:3000"}) as client:
        yield client


@pytest.fixture
def owner(client):
    result = client.post("/v1/auth/register", json={"email": "owner@example.com", "password": "test-password-very-long"})
    assert result.status_code == 201, result.text
    return client


@pytest.fixture
def project(owner):
    result = owner.post("/v1/projects", json={"name": "Acme Knowledge", "description": "Test sources"})
    assert result.status_code == 201, result.text
    return result.json()
