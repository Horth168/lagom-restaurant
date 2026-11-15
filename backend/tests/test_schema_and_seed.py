import subprocess
import sys
from pathlib import Path

from decimal import Decimal

from sqlalchemy import func, select

from app.models import Category, DiningTable, Product, RecipeItem, User
from app.services.app_settings import usd_cents_to_khr
from scripts.seed_demo import seed

BACKEND = Path(__file__).resolve().parents[1]


def test_seed_demo_data(db):
    result = seed(db)
    assert result["products"] > 20
    assert db.scalar(select(func.count()).select_from(Category)) == 11
    latte = db.scalar(select(Product).where(Product.name_en == "Iced Latte"))
    assert latte.effective_station == "DRINKS"
    assert {g.name_en for g in latte.option_groups} == {"Size", "Sugar", "Ice", "Extras"}
    assert db.scalar(select(func.count()).select_from(RecipeItem).where(RecipeItem.product_id == latte.id)) >= 4
    # QR tokens are long and unique
    tokens = db.scalars(select(DiningTable.qr_token)).all()
    assert len(tokens) == 12 and len(set(tokens)) == 12 and all(len(t) >= 40 for t in tokens)
    assert db.scalar(select(func.count()).select_from(User)) == 6
    # running again does nothing
    assert seed(db) == {"skipped": True}


def test_khr_conversion_rounds_to_100_riel():
    assert usd_cents_to_khr(275, Decimal("4100")) == 11300  # 11,275 -> 11,300
    assert usd_cents_to_khr(100, Decimal("4100")) == 4100


def test_migrations_upgrade_and_downgrade(tmp_path):
    env = {"DATABASE_URL": f"sqlite:///{(tmp_path / 'm.db').as_posix()}", "ENVIRONMENT": "test",
           "PATH": "", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}
    for args in (["upgrade", "head"], ["check"], ["downgrade", "base"]):
        r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def test_demo_accounts_can_sign_in(client, SessionTest):
    from scripts.seed_demo import DEMO_PASSWORD
    with SessionTest() as s:
        seed(s)
    r = client.post("/api/auth/login", json={"email": "owner@lagom.test", "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
