import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import auth
from app.db import get_db, make_engine
from app.main import app
from app.models import AppUser, Base

PASSWORD = "test-password-123"


@pytest.fixture()
def db_session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        s.add(AppUser(username="tester", password_hash=auth.hash_password(PASSWORD), role="admin", status="active"))
        s.commit()
    yield factory
    engine.dispose()


@pytest.fixture()
def client(db_session):
    def override():
        with db_session() as s:
            yield s

    app.dependency_overrides[get_db] = override
    auth.reset_limiters()
    yield TestClient(app)  # 不進入 lifespan，避免對實際資料目錄跑 migration
    app.dependency_overrides.clear()


@pytest.fixture()
def authed(client):
    r = client.post("/api/v1/auth/login", json={"username": "tester", "password": PASSWORD})
    assert r.status_code == 200
    return client
