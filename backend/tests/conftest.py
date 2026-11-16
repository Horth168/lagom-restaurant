import os

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"  # in-memory
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-0123456789"
# Tests must not depend on a developer's local backend/.env
for _k in ("PAYWAY_SIMULATOR", "ABA_PAYWAY_MERCHANT_ID", "ABA_PAYWAY_API_KEY", "TELEGRAM_BOT_TOKEN"):
    os.environ[_k] = ""
os.environ["PAYWAY_SIMULATOR"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.rate_limit import limiter  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.models.enums import Role  # noqa: E402

PASSWORD = "Test-password-123"


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(eng, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def SessionTest(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(SessionTest):
    with SessionTest() as s:
        yield s


@pytest.fixture
def client(SessionTest):
    def _get_db():
        s = SessionTest()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    limiter.reset()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db):
    def _make(role: Role, email: str | None = None, **kw) -> User:
        u = User(
            email=email or f"{role.value.lower()}@test.com",
            full_name=f"{role.value.title()} Person",
            role=role,
            password_hash=hash_password(PASSWORD),
            **kw,
        )
        db.add(u)
        db.commit()
        return u

    return _make


@pytest.fixture
def login(client):
    def _login(email: str, password: str = PASSWORD) -> dict:
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login


@pytest.fixture
def owner_headers(make_user, login):
    make_user(Role.OWNER)
    return login("owner@test.com")
