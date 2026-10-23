import io
import json
from datetime import date, timedelta

from PIL import Image

from tests.conftest import PASSWORD

V = {"vehicle_type": "scooter", "energy_type": "gasoline", "brand": "T", "model": "125", "plate": "AAA-1111"}
API = "/api/v1"
TODAY = date.today()


def mk(c, **over):
    r = c.post(f"{API}/vehicles", json={**V, **over})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def energy(c, vid, d, odo, q=3.0, p=30.0, **kw):
    body = {"log_date": str(d), "odometer_km": odo, "quantity": q, "unit_price": p, "energy_source": "gas_95", **kw}
    r = c.post(f"{API}/vehicles/{vid}/energy-logs", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def register(client, username, password="another-pass-1", token=None):
    return client.post(f"{API}/auth/register", json={"username": username, "password": password, "setup_token": token})


# ───────── 註冊與管理員 ─────────
def test_first_registered_user_is_admin_and_logged_in(client, db_session):
    from sqlalchemy import delete

    from app.models import AppUser

    with db_session() as s:  # 移除 fixture 預建帳號，模擬全新安裝
        s.execute(delete(AppUser))
        s.commit()
    st = client.get(f"{API}/auth/registration").json()
    assert st["has_users"] is False and st["can_register"] is True

    r = register(client, "owner")
    assert r.status_code == 201 and r.json()["role"] == "admin"
    assert client.get(f"{API}/auth/me").json()["role"] == "admin"  # 已自動登入
    assert client.get(f"{API}/admin/overview").status_code == 200


def test_registration_closed_by_default_then_approval_flow(authed, client):
    assert register(client, "second").status_code == 403  # 預設關閉

    r = client.put(f"{API}/admin/settings", json={"registration_mode": "approval"})
    assert r.status_code == 200
    reg = register(client.__class__(client.app), "second")  # 另一個未登入的 client
    assert reg.status_code == 201 and reg.json()["pending"] is True

    other = client.__class__(client.app)
    assert other.post(f"{API}/auth/login", json={"username": "second", "password": "another-pass-1"}).status_code == 403

    users = authed.get(f"{API}/admin/users").json()
    uid = next(u["id"] for u in users if u["username"] == "second")
    assert authed.patch(f"{API}/admin/users/{uid}", json={"status": "active"}).status_code == 200
    assert other.post(f"{API}/auth/login", json={"username": "second", "password": "another-pass-1"}).status_code == 200
    # 一般使用者不能進後台
    assert other.get(f"{API}/admin/users").status_code == 403


def test_setup_token_required_for_first_user(client, db_session, monkeypatch):
    from sqlalchemy import delete

    from app.config import get_settings
    from app.models import AppUser

    with db_session() as s:
        s.execute(delete(AppUser))
        s.commit()
    monkeypatch.setattr(get_settings(), "setup_token", "s3cret-token")
    assert client.get(f"{API}/auth/registration").json()["needs_setup_token"] is True
    assert register(client, "owner", token="wrong").status_code == 403
    assert register(client, "owner", token="s3cret-token").status_code == 201


def test_cannot_remove_last_admin_or_self(authed):
    me = next(u for u in authed.get(f"{API}/admin/users").json() if u["username"] == "tester")
    assert authed.patch(f"{API}/admin/users/{me['id']}", json={"role": "user"}).status_code == 400
    assert authed.patch(f"{API}/admin/users/{me['id']}", json={"status": "disabled"}).status_code == 400
    assert authed.delete(f"{API}/admin/users/{me['id']}").status_code == 400


def test_admin_events_record_login_and_failures(authed, client):
    client.post(f"{API}/auth/login", json={"username": "tester", "password": "bad"})
    ev = authed.get(f"{API}/admin/events?kind=login").json()
    assert any(e["success"] is False and e["username"] == "tester" for e in ev)
    assert any(e["success"] for e in ev)
    assert "bad" not in json.dumps([e.get("password") for e in ev])  # 事件欄位不含密碼
    assert authed.get(f"{API}/admin/overview").json()["failed_logins_24h"] >= 1


def test_disabled_user_loses_access_immediately(authed, client):
    authed.put(f"{API}/admin/settings", json={"registration_mode": "open"})
    other = client.__class__(client.app)
    assert register(other, "bob").status_code == 201
    assert other.get(f"{API}/auth/me").status_code == 200
    uid = next(u["id"] for u in authed.get(f"{API}/admin/users").json() if u["username"] == "bob")
    authed.patch(f"{API}/admin/users/{uid}", json={"status": "disabled"})
    assert other.get(f"{API}/auth/me").status_code == 401


def test_users_cannot_see_each_others_data(authed, client):
    vid = mk(authed)
    authed.put(f"{API}/admin/settings", json={"registration_mode": "open"})
    other = client.__class__(client.app)
    register(other, "carol")
    assert other.get(f"{API}/vehicles").json() == []
    for path in (f"/vehicles/{vid}", f"/vehicles/{vid}/energy-logs", f"/vehicles/{vid}/maintenance/status",
                 f"/vehicles/{vid}/compliance", f"/vehicles/{vid}/reports/annual?year=2026"):
        assert other.get(API + path).status_code == 404, path
    assert other.post(f"{API}/vehicles/{vid}/energy-logs", json={}).status_code in (404, 422)


# ───────── 油電車 ─────────
def test_hybrid_uses_fuel_for_efficiency_but_accepts_charging(authed):
    vid = mk(authed, vehicle_type="car", energy_type="hybrid", battery_kwh=12.0)
    energy(authed, vid, TODAY - timedelta(days=30), 1000, q=30, p=30)
    ch = authed.post(f"{API}/vehicles/{vid}/energy-logs", json={
        "log_date": str(TODAY - timedelta(days=20)), "odometer_km": 1100, "quantity": 8, "unit_price": 3,
        "energy_source": "home", "is_full": True})
    assert ch.status_code == 201 and ch.json()["unit"] == "kWh"
    r = energy(authed, vid, TODAY - timedelta(days=10), 1600, q=25, p=30)
    assert r["efficiency"] == 24.0  # 600 km / 25 L，充電記錄不影響 km/L
    dash = authed.get(f"{API}/vehicles/{vid}/dashboard").json()
    assert dash["efficiency_unit"] == "km/L" and dash["avg_efficiency"] == 24.0


def test_hybrid_only_for_cars(authed):
    r = authed.post(f"{API}/vehicles", json={**V, "energy_type": "hybrid"})
    assert r.status_code == 422


# ───────── 保養 ─────────
def test_template_apply_and_status_prediction(authed):
    vid = mk(authed, initial_odometer_km=10000)
    energy(authed, vid, TODAY - timedelta(days=60), 10000)
    energy(authed, vid, TODAY, 12100)  # 60 天 2100 km = 35 km/日
    r = authed.post(f"{API}/vehicles/{vid}/maintenance-items/apply-template",
                    json={"baseline_date": str(TODAY - timedelta(days=60)), "baseline_km": 10000})
    assert r.json()["created"] > 5
    again = authed.post(f"{API}/vehicles/{vid}/maintenance-items/apply-template", json={}).json()
    assert again["created"] == 0  # 不重複建立

    st = authed.get(f"{API}/vehicles/{vid}/maintenance/status").json()
    assert st["current_km"] == 12100 and abs(st["daily_km"] - 35) < 1
    oil = next(i for i in st["items"] if i["name"] == "機油")  # 2000 km / 6 個月
    assert oil["state"] == "overdue" and oil["remaining_km"] == -100

    # 進廠更換機油後，狀態重置
    visit = authed.post(f"{API}/vehicles/{vid}/service-visits", json={
        "visit_date": str(TODAY), "odometer_km": 12100, "shop": "車行",
        "lines": [{"item_id": oil["item_id"], "description": "換機油", "part_name": "10W40", "cost": 400}]})
    assert visit.status_code == 201 and visit.json()["total_cost"] == 400
    st = authed.get(f"{API}/vehicles/{vid}/maintenance/status").json()
    oil = next(i for i in st["items"] if i["name"] == "機油")
    assert oil["state"] == "ok" and oil["last_km"] == 12100 and oil["remaining_km"] == 2000
    assert oil["basis"] == "km"  # 35 km/日 → 57 天，比 6 個月先到


def test_custom_item_needs_an_interval_and_visit_line_validation(authed):
    vid = mk(authed)
    assert authed.post(f"{API}/vehicles/{vid}/maintenance-items", json={"name": "X"}).status_code == 422
    other = mk(authed)
    item = authed.post(f"{API}/vehicles/{other}/maintenance-items", json={"name": "Y", "interval_km": 1000}).json()
    r = authed.post(f"{API}/vehicles/{vid}/service-visits", json={
        "visit_date": str(TODAY), "odometer_km": 100, "lines": [{"item_id": item["id"], "cost": 1}]})
    assert r.status_code == 422  # 不可引用別台車的項目


# ───────── 稅費 / 罰單 / etag ─────────
def test_compliance_status_pay_and_renew(authed):
    vid = mk(authed)
    soon = authed.post(f"{API}/vehicles/{vid}/compliance", json={
        "kind": "license_tax", "due_date": str(TODAY + timedelta(days=6)), "amount": 1620, "recurrence_months": 12}).json()
    assert soon["state"] == "due_soon" and soon["level"] == 2
    late = authed.post(f"{API}/vehicles/{vid}/compliance", json={
        "kind": "inspection", "due_date": str(TODAY - timedelta(days=3))}).json()
    assert late["state"] == "overdue"

    paid = authed.post(f"{API}/compliance/{soon['id']}/pay", json={}).json()
    assert paid["next_id"]
    items = authed.get(f"{API}/vehicles/{vid}/compliance").json()
    nxt = next(i for i in items if i["id"] == paid["next_id"])
    assert nxt["due_date"] == str(date(TODAY.year + 1, (TODAY + timedelta(days=6)).month, (TODAY + timedelta(days=6)).day)) or nxt["state"] == "ok"
    assert authed.post(f"{API}/compliance/{soon['id']}/pay", json={}).status_code == 409
    upcoming = authed.get(f"{API}/compliance/upcoming").json()
    assert {u["kind"] for u in upcoming} >= {"inspection", "license_tax"}


def test_attention_aggregates_everything(authed):
    vid = mk(authed)
    authed.post(f"{API}/vehicles/{vid}/compliance", json={"kind": "compulsory_ins", "due_date": str(TODAY + timedelta(days=1))})
    authed.post(f"{API}/vehicles/{vid}/fines", json={"violation_date": str(TODAY), "amount": 900,
                                                     "due_date": str(TODAY - timedelta(days=1)), "violation": "違停"})
    items = authed.get(f"{API}/attention").json()
    kinds = {(i["kind"], i["severity"]) for i in items}
    assert ("compliance", "critical") in kinds and ("fine", "critical") in kinds
    assert items[0]["severity"] == "critical"


def test_fines_csv_import_dedupes_and_handles_roc_dates(authed):
    vid = mk(authed)
    csv_bytes = "違規日期,金額,違規單號,違規事由\n115/03/04,900,A123,違規停車\n115/03/05,600,A124,超速\n".encode("utf-8-sig")
    r = authed.post(f"{API}/vehicles/{vid}/fines/import", files={"file": ("f.csv", io.BytesIO(csv_bytes), "text/csv")})
    assert r.json() == {"added": 2, "skipped": 0}
    r = authed.post(f"{API}/vehicles/{vid}/fines/import", files={"file": ("f.csv", io.BytesIO(csv_bytes), "text/csv")})
    assert r.json() == {"added": 0, "skipped": 2}
    fines = authed.get(f"{API}/vehicles/{vid}/fines").json()
    assert {f["violation_date"] for f in fines} == {"2026-03-04", "2026-03-05"}
    bad = authed.post(f"{API}/vehicles/{vid}/fines/import", files={"file": ("f.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")})
    assert bad.status_code == 422
    assert authed.post(f"{API}/vehicles/{vid}/fines/lookup").json()["demo"] is True


def test_etag_balance(authed):
    vid = mk(authed)
    for kind, amt in (("topup", 500), ("toll", 40), ("toll", 25), ("balance_adjust", -5)):
        assert authed.post(f"{API}/vehicles/{vid}/etag",
                           json={"entry_date": str(TODAY), "kind": kind, "amount": amt}).status_code == 201
    assert authed.get(f"{API}/vehicles/{vid}/etag").json()["balance"] == 430
    assert authed.post(f"{API}/vehicles/{vid}/etag", json={"entry_date": str(TODAY), "kind": "toll", "amount": -1}).status_code == 422


# ───────── 附件 ─────────
def _jpeg_with_exif(size=(3000, 2000)):
    img = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"  # Make
    exif[0x8825] = {1: "N", 2: (25.0, 2.0, 0.0)}  # GPS IFD
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_attachment_upload_strips_exif_resizes_and_isolates(authed, client, tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    vid = mk(authed)
    log = energy(authed, vid, TODAY, 100)
    raw = _jpeg_with_exif()
    assert Image.open(io.BytesIO(raw)).getexif()  # 原圖確實有 EXIF
    r = authed.post(f"{API}/attachments", data={"owner_type": "energy_log", "owner_id": str(log["id"])},
                    files={"file": ("receipt.jpg", io.BytesIO(raw), "image/jpeg")})
    assert r.status_code == 201, r.text
    att = r.json()
    body = authed.get(att["url"])
    assert body.status_code == 200
    out = Image.open(io.BytesIO(body.content))
    assert max(out.size) == 1600 and len(body.content) < len(raw)
    assert not out.getexif() and "exif" not in out.info  # 中繼資料全部移除
    thumb = Image.open(io.BytesIO(authed.get(att["thumb_url"]).content))
    assert max(thumb.size) == 320
    assert len(authed.get(f"{API}/attachments?owner_type=energy_log&owner_id={log['id']}").json()) == 1

    authed.put(f"{API}/admin/settings", json={"registration_mode": "open"})
    other = client.__class__(client.app)
    register(other, "dave")
    assert other.get(att["url"]).status_code == 404

    bad = authed.post(f"{API}/attachments", data={"owner_type": "energy_log", "owner_id": str(log["id"])},
                      files={"file": ("x.jpg", io.BytesIO(b"not an image"), "image/jpeg")})
    assert bad.status_code == 422
    assert authed.delete(f"{API}/attachments/{att['id']}").status_code == 204
    assert authed.get(att["url"]).status_code == 404


# ───────── 報表 ─────────
def test_annual_report_and_compare(authed):
    vid = mk(authed, initial_odometer_km=1000)
    year = TODAY.year
    energy(authed, vid, date(year, 1, 10), 1000, q=3, p=30)
    energy(authed, vid, date(year, 2, 10), 1300, q=7.5, p=30)  # 300 km，225 元
    authed.post(f"{API}/vehicles/{vid}/service-visits", json={"visit_date": f"{year}-02-15", "odometer_km": 1310,
                                                              "total_cost": 500, "lines": [{"description": "換機油"}]})
    c = authed.post(f"{API}/vehicles/{vid}/compliance", json={"kind": "license_tax", "due_date": f"{year}-04-30",
                                                             "amount": 1620}).json()
    authed.post(f"{API}/compliance/{c['id']}/pay", json={"paid_date": f"{year}-04-20", "create_next": False})
    authed.post(f"{API}/vehicles/{vid}/fines", json={"violation_date": f"{year}-05-01", "amount": 900})
    authed.post(f"{API}/vehicles/{vid}/expenses", json={"expense_date": f"{year}-05-02", "category": "parking", "amount": 100})

    rep = authed.get(f"{API}/vehicles/{vid}/reports/annual?year={year}").json()
    cats = {c["key"]: c["amount"] for c in rep["categories"]}
    assert cats == {"energy": 90 + 225, "maintenance": 500, "tax": 1620, "insurance": 0, "inspection": 0,
                    "fines": 900, "other": 100}
    assert rep["total_cost"] == 315 + 500 + 1620 + 900 + 100
    assert rep["distance_km"] == 310  # 1000 → 1310（最後一次進廠里程）
    assert rep["cost_per_km"] == round(rep["total_cost"] / 310, 2)

    assert authed.post(f"{API}/vehicles/{vid}/reports/annual?year={year}").status_code == 201
    assert len(authed.get(f"{API}/vehicles/{vid}/reports/annual/saved").json()) == 1

    vid2 = mk(authed, brand="Second")
    energy(authed, vid2, date(year, 1, 5), 0, q=3, p=30)
    cmp_ = authed.get(f"{API}/reports/compare?vehicle_ids={vid},{vid2}&from={year}-01-01&to={year}-12-31").json()
    assert len(cmp_) == 2 and cmp_[0]["total_cost"] == rep["total_cost"]
    assert authed.get(f"{API}/reports/compare?vehicle_ids={vid}&from={year}-01-01&to={year}-12-31").status_code == 422


def test_service_history_html_and_pdf(authed):
    vid = mk(authed, brand="Yamaha", model="勁戰")
    authed.post(f"{API}/vehicles/{vid}/service-visits", json={
        "visit_date": str(TODAY), "odometer_km": 5000, "shop": "示範車行", "technician_note": "皮帶輕微龜裂",
        "lines": [{"description": "更換皮帶", "part_name": "原廠皮帶", "cost": 1200}]})
    html = authed.get(f"{API}/vehicles/{vid}/reports/service-history.html")
    assert html.status_code == 200 and "示範車行" in html.text and "更換皮帶" in html.text
    pdf = authed.get(f"{API}/vehicles/{vid}/reports/service-history.pdf")
    assert pdf.status_code in (200, 501)
    if pdf.status_code == 200:
        assert pdf.content.startswith(b"%PDF")


# ───────── 匯出入 / 備份 / 排程 ─────────
def test_import_is_scoped_to_current_user_and_remaps_ids(authed, client):
    vid = mk(authed, brand="Mine")
    energy(authed, vid, TODAY - timedelta(days=10), 100)
    energy(authed, vid, TODAY, 250)
    item = authed.post(f"{API}/vehicles/{vid}/maintenance-items", json={"name": "機油", "interval_km": 2000}).json()
    authed.post(f"{API}/vehicles/{vid}/service-visits", json={
        "visit_date": str(TODAY), "odometer_km": 250, "lines": [{"item_id": item["id"], "cost": 300}]})
    payload = authed.get(f"{API}/data/export?format=json").json()
    assert payload["version"] == 2 and len(payload["service_lines"]) == 1

    authed.put(f"{API}/admin/settings", json={"registration_mode": "open"})
    other = client.__class__(client.app)
    register(other, "erin")
    mk(other, brand="Erin's")

    def up(content):
        return {"file": ("x.json", io.BytesIO(json.dumps(content).encode()), "application/json")}

    assert authed.post(f"{API}/data/import?dry_run=false", files=up(payload)).status_code == 200
    mine = authed.get(f"{API}/vehicles").json()
    assert [v["brand"] for v in mine] == ["Mine"]
    assert [v["brand"] for v in other.get(f"{API}/vehicles").json()] == ["Erin's"]  # 別人的資料不受影響
    new_vid = mine[0]["id"]
    visits = authed.get(f"{API}/vehicles/{new_vid}/service-visits").json()
    assert visits[0]["lines"][0]["item_name"] == "機油"  # 關聯正確重建

    broken = json.loads(json.dumps(payload))
    broken["service_lines"][0]["visit_id"] = 9999
    assert authed.post(f"{API}/data/import?dry_run=true", files=up(broken)).status_code == 422


def test_backup_contains_db_and_uploads(tmp_path):
    import tarfile
    import sqlite3

    from app.services.backup import make_backup

    data = tmp_path / "data"
    (data / "uploads" / "1").mkdir(parents=True)
    (data / "uploads" / "1" / "a.jpg").write_bytes(b"jpg")
    con = sqlite3.connect(data / "motoq.db")
    con.execute("create table t(x)")
    con.execute("insert into t values (42)")
    con.commit()
    con.close()

    for _ in range(3):
        out = make_backup(data, tmp_path / "out", keep=2)
    assert len(list((tmp_path / "out").glob("*.tar.gz"))) == 2
    with tarfile.open(out) as tar:
        names = tar.getnames()
        assert "motoq.db" in names and "uploads/1/a.jpg" in names


def test_scheduler_generates_annual_reports_once(authed, monkeypatch, db_session):
    from app import scheduler

    vid = mk(authed)
    energy(authed, vid, TODAY, 100)
    monkeypatch.setattr(scheduler, "_session_factory", lambda: db_session)
    assert scheduler.generate_annual_reports(TODAY.year) == 1
    assert scheduler.generate_annual_reports(TODAY.year) == 0  # 不重複
    saved = authed.get(f"{API}/vehicles/{vid}/reports/annual/saved").json()
    assert saved[0]["trigger"] == "auto"


CPC_SAMPLE = json.dumps([
    {"型別名稱": "汽柴油零售", "產品名稱": "98無鉛汽油", "交貨地點": "中油自營站", "參考牌價_金額": 34.7, "牌價生效日期": "1151012"},
    {"型別名稱": "汽柴油零售", "產品名稱": "95無鉛汽油", "交貨地點": "中油自營站", "參考牌價_金額": 32.7, "牌價生效日期": "1151012"},
    {"型別名稱": "汽柴油零售", "產品名稱": "92無鉛汽油", "交貨地點": "中油自營站", "參考牌價_金額": 31.2, "牌價生效日期": "1151012"},
    {"型別名稱": "汽柴油零售", "產品名稱": "酒精汽油", "交貨地點": "中油自營站", "參考牌價_金額": 32.7, "牌價生效日期": "1151012"},
    {"型別名稱": "汽柴油零售", "產品名稱": "超級柴油", "交貨地點": "中油自營站", "參考牌價_金額": 29.9, "牌價生效日期": "1151012"},
    {"型別名稱": "汽柴油零售", "產品名稱": "海運輕柴油", "交貨地點": "中油自營站", "參考牌價_金額": 20.0, "牌價生效日期": "1151012"},
    {"型別名稱": "汽柴油零售", "產品名稱": "95無鉛汽油", "交貨地點": "車隊卡", "參考牌價_金額": 1.0, "牌價生效日期": "1151012"},
], ensure_ascii=False)


def test_cpc_parse_real_format():
    from app.services import fuel

    prices, eff = fuel.parse_cpc(CPC_SAMPLE)
    assert prices == {"gas_98": 34.7, "gas_95": 32.7, "gas_92": 31.2, "diesel": 29.9}
    assert eff == date(2026, 10, 12)  # 民國 115/10/12
    assert fuel.parse_cpc("<html>Request Rejected</html>") == ({}, None)
    assert fuel.parse_cpc("{}") == ({}, None)


def test_fuel_latest_change_and_manual_price(authed, db_session):
    from app.services import fuel

    with db_session() as s:
        fuel.store_prices(s, {"gas_95": 30.0}, on=TODAY - timedelta(days=7))
        fuel.store_prices(s, {"gas_95": 30.5}, on=TODAY)
    fuel._last_success = 10**12  # 視為剛更新過，避免測試時對外連線
    latest = authed.get(f"{API}/fuel-prices/latest").json()
    assert latest[0]["price"] == 30.5 and latest[0]["change"] == 0.5
    assert authed.post(f"{API}/fuel-prices", json={"price_date": str(TODAY), "product": "gas_95", "price": 31.2}).status_code == 201


def test_price_suggestion_follows_grade_and_station(authed, db_session):
    from app.services import fuel

    fuel._last_success = 10**12
    with db_session() as s:
        fuel.store_prices(s, {"gas_92": 31.2, "gas_95": 32.7, "gas_98": 34.7}, on=TODAY - timedelta(days=3))
    vid = mk(authed)

    def ask(source, station=""):
        return authed.get(f"{API}/vehicles/{vid}/energy-logs/price-suggestion",
                          params={"energy_source": source, "station": station}).json()

    # 換油品，建議單價跟著換
    assert ask("gas_92", "中油")["price"] == 31.2
    assert ask("gas_95", "中油")["price"] == 32.7
    assert ask("gas_98", "中油")["price"] == 34.7
    assert ask("gas_95", "台塑")["basis"] == "cpc_reference"  # 還沒在台塑加過 → 參考中油

    # 牌價生效「之後」在台塑加過油 → 用實付價
    energy(authed, vid, TODAY - timedelta(days=1), 1000, q=5, p=32.2, station="台塑")
    s = ask("gas_95", "台塑")
    assert s["price"] == 32.2 and s["basis"] == "last_at_station"
    assert ask("gas_95", "中油")["price"] == 32.7  # 中油永遠用牌價
    assert ask("gas_92", "台塑")["basis"] == "cpc_reference"  # 其他油品不沿用 95 的價格
    # 與車輛能源類型不符
    assert authed.get(f"{API}/vehicles/{vid}/energy-logs/price-suggestion",
                      params={"energy_source": "home"}).status_code == 422


TAIPEI_OK = json.dumps({"Result": {
    "CarID": "ABC-1234", "CarType": "M", "TotalCount": 2, "TotalAmount": 350.0,
    "Bills": [{"BillNo": "A001", "ParkingDate": "2026-09-30 10:00", "PayLimitDate": "2026-10-30",
               "BillStatus": 1, "ParkingHours": 2.0, "Amount": 40, "PayAmount": 40}],
    "Reminders": [{"ReminderNo": "R001", "ReminderLimitDate": "2026-10-20", "Amount": 300, "ExtraCharge": 10,
                   "PayAmount": 310, "Bills": [], "IsProsecuted": 0, "ProsecuteLimitDate": "2026-11-20"}],
    "CityCode": "TPE", "AuthorityCode": "", "UpdateTime": "2026-10-11 05:00"},
    "Status": "SUCCESS", "Message": "查詢成功"}, ensure_ascii=False).encode()
TAIPEI_NONE = b'{"Result": null, "Status": "SUCCESS", "Message": "ok"}'


class _FakeResp:
    def __init__(self, body):
        self.body = body

    def read(self, n=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_parking(monkeypatch, handler):
    from app.services import parking

    monkeypatch.setattr(parking, "open_url", handler)
    monkeypatch.setattr(parking, "MIN_INTERVAL", 0)
    parking._cache.clear()
    return parking


def test_parking_lookup_multi_city(authed, monkeypatch):
    calls = []

    def fake_open(req, timeout=0):
        calls.append(req.full_url)
        return _FakeResp(TAIPEI_OK if "ABC-1234" in req.full_url else TAIPEI_NONE)

    _patch_parking(monkeypatch, fake_open)
    r = authed.post(f"{API}/parking/lookup", json={"plate": "abc1234", "car_type": "M", "city": "TPE"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["plate"] == "ABC-1234" and d["total_amount"] == 350 and d["city"] == "臺北市" and d["city_code"] == "TPE"
    assert d["bills"][0]["bill_no"] == "A001" and d["reminders"][0]["pay_amount"] == 310
    assert calls[0] == "https://trafficapi.pma.gov.taipei/Parking/PayBill/CarID/ABC-1234/CarType/M"

    # 同一車牌改查新北：打到新北的端點（不同縣市不共用快取）
    authed.post(f"{API}/parking/lookup", json={"plate": "ABC-1234", "car_type": "M", "city": "NWT"})
    assert calls[1].startswith("https://trafficapi.traffic.ntpc.gov.tw/Parking/PayBill/CarID/ABC-1234")
    # 快取：重複查詢不再呼叫官方 API
    authed.post(f"{API}/parking/lookup", json={"plate": "ABC-1234", "car_type": "M", "city": "TPE"})
    assert len(calls) == 2

    # 臺中官方只有 http，要標示出來
    t = authed.post(f"{API}/parking/lookup", json={"plate": "XYZ-0000", "car_type": "C", "city": "TXG"}).json()
    assert t["insecure"] is True and t["total_count"] == 0 and t["bills"] == []

    # 驗證與稽核（只記遮蔽後的車牌）
    assert authed.post(f"{API}/parking/lookup", json={"plate": "ab c;", "car_type": "M", "city": "TPE"}).status_code == 422
    assert authed.post(f"{API}/parking/lookup", json={"plate": "ABC-1234", "car_type": "X", "city": "TPE"}).status_code == 422
    assert authed.post(f"{API}/parking/lookup", json={"plate": "ABC-1234", "car_type": "M", "city": "ZZZ"}).status_code == 422
    ev = authed.get(f"{API}/admin/events?kind=parking_lookup").json()
    assert any("ABC-12**" in e["detail"] for e in ev)
    assert not any("ABC-1234" in e["detail"] for e in ev)
    assert len(authed.get(f"{API}/parking/cities").json()) == 21


def test_parking_result_is_saved_for_vehicle_and_shows_in_attention(authed, monkeypatch):
    _patch_parking(monkeypatch, lambda req, timeout=0: _FakeResp(TAIPEI_OK))
    vid = mk(authed, plate="ABC-1234")
    r = authed.post(f"{API}/parking/lookup",
                    json={"plate": "ABC1234", "car_type": "M", "city": "TPE", "vehicle_id": vid})
    assert r.status_code == 200
    checks = authed.get(f"{API}/vehicles/{vid}/parking-checks").json()
    assert checks[0]["city"] == "臺北市" and checks[0]["total_amount"] == 350
    items = authed.get(f"{API}/attention").json()
    assert any(i["kind"] == "parking" and "350" in i["title"] for i in items)

    # 查別人的車牌不會存到這台車
    authed.post(f"{API}/parking/lookup", json={"plate": "ZZZ-9999", "car_type": "M", "city": "NWT", "vehicle_id": vid})
    assert len(authed.get(f"{API}/vehicles/{vid}/parking-checks").json()) == 1


def test_parking_upstream_failure(authed, monkeypatch):
    import urllib.error

    def boom(req, timeout=0):
        raise urllib.error.URLError("down")

    _patch_parking(monkeypatch, boom)
    r = authed.post(f"{API}/parking/lookup", json={"plate": "AAA-0001", "car_type": "C", "city": "KHH"})
    assert r.status_code == 502 and "高雄市" in r.json()["detail"]


def test_parking_auto_check_is_opt_in(authed, monkeypatch, db_session):
    from app.routers import parking as parking_router

    calls = []

    def fake_open(req, timeout=0):
        calls.append(req.full_url)
        return _FakeResp(TAIPEI_OK)

    _patch_parking(monkeypatch, fake_open)
    vid = mk(authed, plate="ABC-1234")
    with db_session() as s:
        assert parking_router.run_auto_checks(s) == 0  # 預設關閉，不會把車牌送出去
    assert calls == []

    authed.put(f"{API}/settings", json={"parking_auto_check": True, "parking_cities": ["TPE", "NWT"]})
    with db_session() as s:
        assert parking_router.run_auto_checks(s) == 2
    assert len(calls) == 2
    assert {c["city_code"] for c in authed.get(f"{API}/vehicles/{vid}/parking-checks").json()} == {"TPE", "NWT"}
    assert authed.put(f"{API}/settings", json={"parking_cities": ["NOPE"]}).status_code == 422


def test_plate_normalization():
    from app.services.parking import car_type_for, normalize_plate

    assert normalize_plate("abc1234") == "ABC-1234"
    assert normalize_plate("ABC-1234") == "ABC-1234"
    assert normalize_plate("1234ab") == "1234-AB"
    assert car_type_for("car") == "C" and car_type_for("scooter") == "M" and car_type_for("heavy_moto") == "M"


def test_migration_from_v1_assigns_owner_and_admin(tmp_path):
    """舊版（0001）資料庫升級：既有車輛歸第一位使用者，並設為管理員。"""
    import sqlite3

    from alembic import command
    from alembic.config import Config

    from app.main import BACKEND_DIR

    db = tmp_path / "old.db"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "0001")
    con = sqlite3.connect(db)
    con.execute("insert into app_users (username, password_hash, created_at) values ('old', 'x', '2026-01-01')")
    con.execute("insert into vehicles (vehicle_type, energy_type, brand, model, plate, initial_odometer_km, status,"
                " created_at, updated_at) values ('scooter','gasoline','a','b','c',0,'active','2026-01-01','2026-01-01')")
    con.execute("insert into app_settings (key, value) values ('anomaly_drop_pct', '20')")
    con.commit()
    con.close()

    command.upgrade(cfg, "head")
    con = sqlite3.connect(db)
    assert con.execute("select role, status from app_users").fetchone() == ("admin", "active")
    assert con.execute("select user_id from vehicles").fetchone() == (1,)
    assert con.execute("select key, value from user_settings").fetchone() == ("anomaly_drop_pct", 20)
    con.close()


# ───────── 牌照稅估算與 etag 低餘額 ─────────
def test_license_tax_estimate_domain():
    from app.domain.license_tax import estimate, next_due_date

    d = date(2026, 6, 1)
    assert estimate("scooter", "gasoline", 125, d).exempt and estimate("scooter", "gasoline", 150, d).amount == 0
    assert estimate("scooter", "gasoline", 155, d).amount == 800
    assert estimate("scooter", "gasoline", 300, d).amount == 1620
    assert estimate("heavy_moto", "gasoline", 1000, d).amount == 4320
    assert estimate("car", "gasoline", 1798, d).amount == 7120
    assert estimate("car", "hybrid", 1798, d).amount == 7120
    assert estimate("car", "gasoline", 2000, d).amount == 11230
    assert estimate("car", "gasoline", 9000, d).amount == 151200
    assert estimate("car", "electric", None, d).exempt and estimate("car", "electric", None, d).amount == 0
    assert estimate("car", "electric", None, date(2031, 1, 1)).amount is None
    assert estimate("car", "gasoline", None, d).amount is None
    assert next_due_date(date(2026, 4, 30)) == date(2026, 4, 30)
    assert next_due_date(date(2026, 5, 1)) == date(2027, 4, 30)


def test_compliance_estimate_endpoint(authed):
    vid = mk(authed, displacement_cc=250)
    d = authed.get(f"{API}/vehicles/{vid}/compliance/estimate").json()["license_tax"]
    assert d["amount"] == 800 and d["exempt"] is False and d["already_created"] is False
    authed.post(f"{API}/vehicles/{vid}/compliance", json={"kind": "license_tax", "due_date": d["due_date"], "amount": 800})
    assert authed.get(f"{API}/vehicles/{vid}/compliance/estimate").json()["license_tax"]["already_created"] is True


def test_etag_low_balance_goes_to_attention(authed):
    vid = mk(authed)
    assert not any(i["kind"] == "etag" for i in authed.get(f"{API}/attention").json())  # 沒有 etag 記錄不提醒
    authed.post(f"{API}/vehicles/{vid}/etag", json={"entry_date": str(TODAY), "kind": "topup", "amount": 300})
    authed.post(f"{API}/vehicles/{vid}/etag", json={"entry_date": str(TODAY), "kind": "toll", "amount": 150})
    items = authed.get(f"{API}/attention").json()
    assert any(i["kind"] == "etag" and "150" in i["title"] for i in items)
    authed.put(f"{API}/settings", json={"etag_low_balance": 100})
    assert not any(i["kind"] == "etag" for i in authed.get(f"{API}/attention").json())
