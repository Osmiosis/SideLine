import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(jobs_dir=tmp_path / "jobs", start_worker=False)


@pytest.fixture
def client(app):
    return TestClient(app)
