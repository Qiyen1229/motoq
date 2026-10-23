import io
import json

from tests.conftest import PASSWORD

V = {"vehicle_type": "scooter", "energy_type": "gasoline", "brand": "Test", "model": "125", "plate": "AAA-1111"}


def mk_vehicle(c, **over):
    r = c.post("/api/v1/vehicles", json={**V, **over})
    assert r.status_code == 201, r.text
    return r.json()


def add_log(c, vid, day, odo, q=3.0, p=30.0, **kw):
    body = {"log_date": f"2026-02-{day:02d}", "odometer_km": odo, "quantity": q, "unit_price": p,
            "energy_source": "gas_95", **kw}
    return c.post(f"/api/v1/vehicles/{vid}/energy-logs", json=body)


def test_auth_required_and_login_flow(client):
    assert client.get("/api/v1/vehicles").status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "tester", "password": "x"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "tester", "password": PASSWORD}).status_code == 200
    assert client.get("/api/v1/auth/me").json() == {"username": "tester", "role": "admin", "status": "active"}
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/vehicles").status_code == 401


def test_login_rate_limit(client):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"username": "tester", "password": "bad"})
    r = client.post("/api/v1/auth/login", json={"username": "tester", "password": PASSWORD})
    assert r.status_code == 429


def test_energy_flow_and_efficiency(authed):
    v = mk_vehicle(authed, initial_odometer_km=1000)
    vid = v["id"]
    assert add_log(authed, vid, 1, 1000).json()["efficiency"] is None
    r = add_log(authed, vid, 10, 1120, q=None, total_amount=90, unit_price=30.0)  # 自動算公升
    assert r.status_code == 201
    body = r.json()
    assert body["quantity"] == 3.0 and body["efficiency"] == 40.0 and body["unit"] == "L"

    stats = authed.get(f"/api/v1/vehicles/{vid}/efficiency/stats").json()
    assert stats["avg_efficiency"] == 40.0 and stats["cost_per_km"] == 0.75

    dash = authed.get(f"/api/v1/vehicles/{vid}/dashboard").json()
    assert dash["total_km"] == 1120 and dash["efficiency_unit"] == "km/L"
    assert authed.get(f"/api/v1/vehicles/{vid}").json()["current_odometer_km"] == 1120


def test_odometer_decrease_needs_force(authed):
    vid = mk_vehicle(authed)["id"]
    add_log(authed, vid, 1, 5000)
    r = add_log(authed, vid, 5, 4000)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "odometer_decrease"
    r = authed.post(
        f"/api/v1/vehicles/{vid}/energy-logs?force=true",
        json={"log_date": "2026-02-05", "odometer_km": 4000, "quantity": 3, "unit_price": 30, "energy_source": "gas_95"},
    )
    assert r.status_code == 201


def test_odometer_adjustment_keeps_total_continuous(authed):
    vid = mk_vehicle(authed)["id"]
    add_log(authed, vid, 1, 30000)
    add_log(authed, vid, 5, 30120)
    authed.post(f"/api/v1/vehicles/{vid}/odometer-adjustments",
                json={"effective_date": "2026-02-10", "offset_km": 30120, "note": "換儀表"})
    r = add_log(authed, vid, 12, 130)  # 新儀表讀數 130 => 總里程 30250
    assert r.status_code == 201, r.text
    assert r.json()["total_km"] == 30250 and r.json()["distance_km"] == 130


def test_source_must_match_energy_type(authed):
    vid = mk_vehicle(authed)["id"]
    r = authed.post(f"/api/v1/vehicles/{vid}/energy-logs",
                    json={"log_date": "2026-02-01", "odometer_km": 100, "quantity": 2, "unit_price": 5, "energy_source": "home"})
    assert r.status_code == 422


def test_electric_vehicle(authed):
    vid = mk_vehicle(authed, energy_type="electric", battery_kwh=2.6, default_energy_source="home")["id"]
    r = authed.post(f"/api/v1/vehicles/{vid}/energy-logs",
                    json={"log_date": "2026-02-01", "odometer_km": 100, "quantity": 1.5, "unit_price": 4.0,
                          "energy_source": "home"})
    assert r.status_code == 201 and r.json()["unit"] == "kWh" and r.json()["total_amount"] == 6


def test_soft_delete_and_export_import_roundtrip(authed):
    vid = mk_vehicle(authed)["id"]
    log1 = add_log(authed, vid, 1, 1000).json()
    add_log(authed, vid, 8, 1100)
    assert authed.delete(f"/api/v1/energy-logs/{log1['id']}").status_code == 204
    assert len(authed.get(f"/api/v1/vehicles/{vid}/energy-logs").json()) == 1

    exported = authed.get("/api/v1/data/export?format=json")
    assert exported.status_code == 200
    payload = exported.json()
    assert len(payload["energy_logs"]) == 1  # 已刪除者不匯出

    z = authed.get("/api/v1/data/export?format=csv")
    assert z.headers["content-type"] == "application/zip"

    files = {"file": ("x.json", io.BytesIO(json.dumps(payload).encode()), "application/json")}
    dry = authed.post("/api/v1/data/import?dry_run=true", files=files)
    assert dry.json()["counts"]["energy_logs"] == 1

    # 匯入前先新增另一台，確認 replace 之後只剩匯出內容
    mk_vehicle(authed, brand="Other")
    files = {"file": ("x.json", io.BytesIO(json.dumps(payload).encode()), "application/json")}
    # 測試環境未設定 data_dir 快照路徑時仍應可執行
    r = authed.post("/api/v1/data/import?dry_run=false", files=files)
    assert r.status_code == 200, r.text
    vehicles = authed.get("/api/v1/vehicles").json()
    assert len(vehicles) == 1 and vehicles[0]["brand"] == "Test"


def test_import_rejects_garbage(authed):
    files = {"file": ("x.json", io.BytesIO(b'{"app":"other"}'), "application/json")}
    assert authed.post("/api/v1/data/import", files=files).status_code == 422


def test_settings_threshold_changes_warning(authed):
    assert authed.get("/api/v1/settings").json()["anomaly_drop_pct"] == 15.0
    r = authed.put("/api/v1/settings", json={"anomaly_drop_pct": 5})
    assert r.json()["anomaly_drop_pct"] == 5


def test_ensure_default_admin(client, db_session, monkeypatch):
    """驗證預設管理員自動初始化邏輯"""
    from app.config import get_settings
    import app.main

    monkeypatch.setattr(app.main, "_session_factory", lambda: db_session)
    monkeypatch.setenv("MOTOQ_DEFAULT_ADMIN_USERNAME", "qiyen")
    monkeypatch.setenv("MOTOQ_DEFAULT_ADMIN_PASSWORD", "test-admin-pw-123")
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.default_admin_username == "qiyen"
    assert settings.default_admin_password == "test-admin-pw-123"

    # 執行初始化管理員
    app.main.ensure_default_admin()

    # 驗證可以用 qiyen / test-admin-pw-123 成功登入，且為最高權限管理者 (role: admin)
    r = client.post("/api/v1/auth/login", json={"username": "qiyen", "password": "test-admin-pw-123"})
    assert r.status_code == 200, r.text
    user_info = r.json()
    assert user_info["username"] == "qiyen"
    assert user_info["role"] == "admin"
    assert user_info["status"] == "active"


