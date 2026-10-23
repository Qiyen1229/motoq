"""維修履歷（賣車用）：產生 HTML，並以 WeasyPrint 轉為 PDF。

HTML 版本永遠可用（可由瀏覽器列印成 PDF）；PDF 需要系統安裝 Pango 與中文字型（Docker 映像已包含）。
"""

from datetime import date
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MaintenanceItem, ServiceLine, ServiceVisit, Vehicle
from app.services.attention import vehicle_label
from app.services.energy import load_state

TYPE_LABEL = {"car": "汽車", "scooter": "機車", "heavy_moto": "重型機車"}
ENERGY_LABEL = {"gasoline": "燃油", "electric": "純電", "hybrid": "油電混合"}

CSS = """
@page { size: A4; margin: 18mm 15mm; @bottom-right { content: counter(page) " / " counter(pages); font-size: 9pt; color: #777; } }
body { font-family: "Noto Sans CJK TC", "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif; color: #1c1c1c; font-size: 10.5pt; }
h1 { font-size: 20pt; margin: 0 0 4px; letter-spacing: .04em; }
.sub { color: #8a6d1d; margin-bottom: 14px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 16px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #ddd; vertical-align: top; }
th { background: #f4efe2; font-weight: 600; }
.kv td:first-child { width: 28%; color: #666; }
.visit { page-break-inside: avoid; margin-bottom: 14px; }
.visit h3 { margin: 0; padding: 6px 8px; background: #1c1c1c; color: #e6c872; font-size: 11pt; }
.num { text-align: right; white-space: nowrap; }
.foot { color: #888; font-size: 9pt; margin-top: 18px; }
"""


def _money(n: int) -> str:
    return f"${n:,}"


def build_html(db: Session, vehicle: Vehicle) -> str:
    st = load_state(db, vehicle)
    visits = db.scalars(
        select(ServiceVisit).where(ServiceVisit.vehicle_id == vehicle.id).order_by(ServiceVisit.visit_date, ServiceVisit.id)
    ).all()
    names = {i.id: i.name for i in db.scalars(select(MaintenanceItem).where(MaintenanceItem.vehicle_id == vehicle.id))}
    total = sum(v.total_cost for v in visits)

    info = [
        ("車輛", f"{TYPE_LABEL.get(vehicle.vehicle_type, '')}・{ENERGY_LABEL.get(vehicle.energy_type, '')}"),
        ("廠牌／車型", " ".join(x for x in (vehicle.brand, vehicle.model) if x) or "—"),
        ("車牌", vehicle.plate or "—"),
        ("排氣量", f"{vehicle.displacement_cc} cc" if vehicle.displacement_cc else "—"),
        ("購入日期", str(vehicle.purchase_date) if vehicle.purchase_date else "—"),
        ("目前里程", f"{st.current_km:,} km"),
        ("維修紀錄", f"{len(visits)} 次，累計 {_money(total)}"),
    ]
    rows = "".join(f"<tr><td>{escape(k)}</td><td>{escape(v)}</td></tr>" for k, v in info)

    blocks = []
    for v in reversed(visits):
        lines = db_lines(db, v.id)
        body = "".join(
            f"<tr><td>{escape(names.get(l.item_id, '') or l.description or '—')}</td>"
            f"<td>{escape(l.part_name)}</td><td class='num'>{_money(l.cost)}</td></tr>"
            for l in lines
        ) or "<tr><td colspan='3' style='color:#999'>（無明細）</td></tr>"
        note = f"<p style='margin:4px 8px'>技師備註：{escape(v.technician_note)}</p>" if v.technician_note else ""
        blocks.append(
            f"<div class='visit'><h3>{v.visit_date}　{v.odometer_km:,} km　{escape(v.shop or '自行保養')}　"
            f"<span style='float:right'>{_money(v.total_cost)}</span></h3>"
            f"<table><tr><th>項目</th><th>零件／說明</th><th class='num'>費用</th></tr>{body}</table>{note}</div>"
        )
    history = "".join(blocks) or "<p style='color:#999'>尚無維修紀錄。</p>"

    return (
        f"<!doctype html><html lang='zh-TW'><head><meta charset='utf-8'><title>維修履歷 {escape(vehicle_label(vehicle))}</title>"
        f"<style>{CSS}</style></head><body>"
        f"<h1>維修履歷</h1><div class='sub'>{escape(vehicle_label(vehicle))}　產生日期 {date.today()}</div>"
        f"<table class='kv'>{rows}</table><h2 style='font-size:13pt'>維修明細（新 → 舊）</h2>{history}"
        f"<div class='foot'>本履歷由 MotoQ 依車主自行記錄的資料產生，僅供參考。</div></body></html>"
    )


def db_lines(db: Session, visit_id: int):
    return db.scalars(select(ServiceLine).where(ServiceLine.visit_id == visit_id).order_by(ServiceLine.id)).all()


def render_pdf(html: str) -> bytes:
    from weasyprint import HTML  # 延遲載入：缺系統函式庫時不影響其他功能

    return HTML(string=html).write_pdf()
