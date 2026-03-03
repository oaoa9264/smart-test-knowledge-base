import os
import sys
import tempfile
import uuid

import pytest

CURRENT_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Use an isolated temporary DB for every test run so existing local data is never touched.
TEST_DB_PATH = os.path.join(
    tempfile.gettempdir(),
    "smart_test_knowledge_base_{0}.db".format(uuid.uuid4().hex),
)
os.environ["DATABASE_URL"] = "sqlite:///{0}".format(TEST_DB_PATH)

from app.core.database import engine
from app.models.entities import Base


def _remove_sqlite_artifacts(db_path: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        target = "{0}{1}".format(db_path, suffix)
        if os.path.exists(target):
            os.remove(target)


@pytest.fixture(autouse=True)
def _reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def pytest_sessionfinish(session, exitstatus):
    _remove_sqlite_artifacts(TEST_DB_PATH)
