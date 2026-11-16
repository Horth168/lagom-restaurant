"""Security checks from the milestone 10 review."""
import io
from datetime import date

from openpyxl import load_workbook

from app.config import get_settings
from app.models.enums import Role


def _try_logins(client, ip_header_values):
    codes = []
    for i, fwd in enumerate(ip_header_values):
        r = client.post("/api/auth/login", headers={"X-Forwarded-For": fwd},
                        json={"email": f"nobody{i}@test.com", "password": "wrong-password"})
        codes.append(r.status_code)
    return codes


def test_faked_forwarded_ip_cannot_bypass_login_limit(client):
    # Without a trusted proxy the header is ignored: 11th wrong login from the same computer is blocked
    codes = _try_logins(client, [f"10.0.0.{i}" for i in range(12)])
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_behind_proxy_only_the_proxy_added_ip_counts(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", 1)
    # The attacker changes the first value every time; the proxy always appends the real IP last
    codes = _try_logins(client, [f"10.0.0.{i}, 203.0.113.7" for i in range(12)])
    assert codes[10] == 429
    # A different real visitor is not blocked
    assert _try_logins(client, ["198.51.100.9"])[0] == 401


def test_excel_export_never_contains_formulas(client, owner_headers):
    today = date.today().isoformat()
    client.post("/api/admin/finance/expenses", headers=owner_headers, json={
        "category": "OTHER", "spent_on": today, "description": '=HYPERLINK("http://evil.example","click")',
        "currency": "USD", "amount_minor": 500})
    r = client.get("/api/admin/finance/report.xlsx?period=today", headers=owner_headers)
    ws = load_workbook(io.BytesIO(r.content))["Expenses"]
    cell = ws.cell(2, 3)
    assert cell.value.startswith("=HYPERLINK") and cell.data_type == "s"  # shown as text, not run


def test_https_only_header_in_production(client, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    assert "strict-transport-security" not in client.get("/api/health").headers  # not on localhost
    monkeypatch.setattr(get_settings(), "environment", "production")
    prod = TestClient(create_app())  # no startup checks here: only the response headers are tested
    prod.app.dependency_overrides = client.app.dependency_overrides
    assert prod.get("/api/health").headers["strict-transport-security"].startswith("max-age=31536000")


def test_production_refuses_unsafe_settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "environment", "production")
    monkeypatch.setattr(s, "khqr_test_mode", True)
    problems = s.validate_for_production()
    assert any("KHQR_TEST_MODE" in p for p in problems)
    monkeypatch.setattr(s, "secret_key", "short")
    assert any("SECRET_KEY" in p for p in s.validate_for_production())
    assert any("PostgreSQL" in p for p in problems)


def test_cashier_cannot_reach_owner_only_endpoints(client, make_user, login):
    make_user(Role.CASHIER)
    h = login("cashier@test.com")
    for method, path in [("get", "/api/admin/finance/report.xlsx?period=today"), ("patch", "/api/settings"),
                         ("get", "/api/staff"), ("get", "/api/admin/audit")]:
        r = getattr(client, method)(path, headers=h, **({"json": {}} if method == "patch" else {}))
        assert r.status_code == 403, path


def test_settings_read_from_real_environment_variables(monkeypatch):
    """Hosting sites (Render) give settings as environment variables, not a .env file."""
    from app.config import Settings

    monkeypatch.setenv("CORS_ORIGINS", "https://order.lagom.example, https://lagom.example")
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    s = Settings(_env_file=None)
    assert s.cors_origins == ["https://order.lagom.example", "https://lagom.example"]
    assert s.trusted_proxy_hops == 1
