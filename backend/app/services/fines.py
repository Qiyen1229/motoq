"""罰單查詢提供者介面。

官方資料源（監理站／警政署）有驗證碼與使用條款限制，這裡不爬取；只定義介面，
預設實作回傳示範資料，之後要接合法管道時只需新增一個 FineProvider。
"""

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol


@dataclass
class FineRecord:
    fine_no: str
    violation_date: date
    violation: str
    location: str
    amount: int
    due_date: date | None
    source: str


class FineProvider(Protocol):
    name: str

    def lookup(self, plate: str) -> list[FineRecord]: ...


class MockFineProvider:
    name = "mock"

    def lookup(self, plate: str) -> list[FineRecord]:
        today = date.today()
        return [
            FineRecord("DEMO-0001", today - timedelta(days=12), "違規停車（示範資料）", "示範路 1 號",
                       900, today + timedelta(days=48), "mock"),
        ]


PROVIDERS: dict[str, FineProvider] = {"mock": MockFineProvider()}

_ALIASES = {
    "fine_no": ("fine_no", "單號", "罰單號碼", "違規單號"),
    "violation_date": ("violation_date", "違規日期", "日期"),
    "violation": ("violation", "違規事由", "違規項目", "事由"),
    "location": ("location", "違規地點", "地點"),
    "amount": ("amount", "金額", "罰款", "罰鍰"),
    "due_date": ("due_date", "應到案日期", "繳費期限", "到案日期"),
    "paid_date": ("paid_date", "繳費日期", "已繳日期"),
}


def _parse_date(s: str) -> date | None:
    s = s.strip().replace("/", "-").replace(".", "-")
    if not s:
        return None
    parts = s.split("-")
    if len(parts) != 3:
        raise ValueError(f"日期格式錯誤：{s}")
    y, m, d = (int(p) for p in parts)
    if y < 1911:  # 民國年
        y += 1911
    return date(y, m, d)


def parse_csv(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV 沒有標題列")
    header = {h.strip(): h for h in reader.fieldnames}
    col = {}
    for field, names in _ALIASES.items():
        col[field] = next((header[n] for n in names if n in header), None)
    if not col["violation_date"] or not col["amount"]:
        raise ValueError("CSV 至少需要「違規日期」與「金額」欄位")
    rows = []
    for n, raw in enumerate(reader, start=2):
        try:
            amount = int(float((raw.get(col["amount"]) or "0").replace(",", "").replace("$", "").strip() or 0))
            rows.append(
                {
                    "fine_no": (raw.get(col["fine_no"]) or "").strip() if col["fine_no"] else "",
                    "violation_date": _parse_date(raw.get(col["violation_date"]) or ""),
                    "violation": (raw.get(col["violation"]) or "").strip() if col["violation"] else "",
                    "location": (raw.get(col["location"]) or "").strip() if col["location"] else "",
                    "amount": amount,
                    "due_date": _parse_date(raw.get(col["due_date"]) or "") if col["due_date"] else None,
                    "paid_date": _parse_date(raw.get(col["paid_date"]) or "") if col["paid_date"] else None,
                }
            )
        except (ValueError, TypeError) as e:
            raise ValueError(f"第 {n} 列：{e}") from e
        if rows[-1]["violation_date"] is None:
            raise ValueError(f"第 {n} 列：缺少違規日期")
    return rows
