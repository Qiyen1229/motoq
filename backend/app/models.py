from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


# ───────────── 帳號與安全 ─────────────
class AppUser(Base):
    __tablename__ = "app_users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user", server_default="user")  # admin|user
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")  # active|pending|disabled
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)


class SecurityEvent(Base):
    """登入、註冊、管理動作的稽核紀錄（不含密碼等敏感內容）。"""

    __tablename__ = "security_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    user_id: Mapped[int | None] = mapped_column(Integer)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AppSetting(Base):
    """全站設定（管理員可調）。"""

    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)


class UserSetting(Base):
    __tablename__ = "user_settings"
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)


# ───────────── 車輛與能源 ─────────────
class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    vehicle_type: Mapped[str] = mapped_column(String(16))  # car|scooter|heavy_moto
    energy_type: Mapped[str] = mapped_column(String(16))  # gasoline|electric|hybrid
    brand: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    plate: Mapped[str] = mapped_column(String(16), default="")
    displacement_cc: Mapped[int | None] = mapped_column(Integer)
    battery_kwh: Mapped[float | None] = mapped_column(Float)
    default_energy_source: Mapped[str | None] = mapped_column(String(16))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_price: Mapped[int | None] = mapped_column(Integer)
    initial_odometer_km: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|sold
    sold_date: Mapped[date | None] = mapped_column(Date)
    sold_price: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class OdometerAdjustment(Base):
    """儀表更換／歸零：effective_date 起，總里程 = 讀數 + offset_km。"""

    __tablename__ = "odometer_adjustments"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"))
    effective_date: Mapped[date] = mapped_column(Date)
    offset_km: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(200), default="")


class EnergyLog(Base):
    __tablename__ = "energy_logs"
    __table_args__ = (Index("ix_energy_logs_vehicle_date", "vehicle_id", "log_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"))
    log_date: Mapped[date] = mapped_column(Date)
    odometer_km: Mapped[int] = mapped_column(Integer)  # 儀表讀數
    quantity: Mapped[float] = mapped_column(Float)  # L 或 kWh
    unit: Mapped[str] = mapped_column(String(8))  # L|kWh
    unit_price: Mapped[float] = mapped_column(Float)
    total_amount: Mapped[int] = mapped_column(Integer)
    is_full: Mapped[bool] = mapped_column(Boolean, default=True)
    missed_before: Mapped[bool] = mapped_column(Boolean, default=False)
    energy_source: Mapped[str] = mapped_column(String(16))
    station: Mapped[str] = mapped_column(String(64), default="")
    start_soc: Mapped[int | None] = mapped_column(Integer)
    end_soc: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


# ───────────── 保養與維修 ─────────────
class MaintenanceItem(Base):
    """耗材／保養項目定義：里程或時間，先到先提醒。"""

    __tablename__ = "maintenance_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32), default="其他")
    interval_km: Mapped[int | None] = mapped_column(Integer)
    interval_months: Mapped[int | None] = mapped_column(Integer)
    baseline_date: Mapped[date | None] = mapped_column(Date)  # 尚無更換記錄時的起算基準
    baseline_km: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ServiceVisit(Base):
    """進廠／自行保養一次；明細在 ServiceLine。也是賣車履歷的來源。"""

    __tablename__ = "service_visits"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    visit_date: Mapped[date] = mapped_column(Date)
    odometer_km: Mapped[int] = mapped_column(Integer)  # 儀表讀數
    shop: Mapped[str] = mapped_column(String(64), default="")
    total_cost: Mapped[int] = mapped_column(Integer, default=0)
    technician_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ServiceLine(Base):
    __tablename__ = "service_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("service_visits.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("maintenance_items.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(String(120), default="")
    part_name: Mapped[str] = mapped_column(String(120), default="")
    cost: Mapped[int] = mapped_column(Integer, default=0)


# ───────────── 稅費、罰單、其他 ─────────────
class ComplianceItem(Base):
    __tablename__ = "compliance_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[int] = mapped_column(Integer, default=0)
    paid_date: Mapped[date | None] = mapped_column(Date)
    provider: Mapped[str] = mapped_column(String(64), default="")
    policy_no: Mapped[str] = mapped_column(String(64), default="")
    recurrence_months: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Fine(Base):
    __tablename__ = "fines"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    fine_no: Mapped[str] = mapped_column(String(64), default="")
    violation_date: Mapped[date] = mapped_column(Date)
    violation: Mapped[str] = mapped_column(String(120), default="")
    location: Mapped[str] = mapped_column(String(120), default="")
    amount: Mapped[int] = mapped_column(Integer, default=0)
    due_date: Mapped[date | None] = mapped_column(Date)
    paid_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual|import|mock
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    expense_date: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(24))  # parking|toll|energy_subscription|wash|accessory|other
    amount: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EtagEntry(Base):
    __tablename__ = "etag_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    entry_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(16))  # topup|toll|balance_adjust
    amount: Mapped[int] = mapped_column(Integer)  # 儲值為正；通行費為正數（扣款）；校正可為負
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ───────────── 附件、報表、油價 ─────────────
class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (Index("ix_attachments_owner", "owner_type", "owner_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id", ondelete="CASCADE"), index=True)
    owner_type: Mapped[str] = mapped_column(String(24))
    owner_id: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String(255))  # 相對於 uploads 目錄
    thumb_path: Mapped[str] = mapped_column(String(255))
    original_name: Mapped[str] = mapped_column(String(120), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AnnualReport(Base):
    __tablename__ = "annual_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual|auto
    snapshot: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FuelPrice(Base):
    __tablename__ = "fuel_prices"
    price_date: Mapped[date] = mapped_column(Date, primary_key=True)
    product: Mapped[str] = mapped_column(String(16), primary_key=True)  # gas_92|gas_95|gas_98|diesel
    price: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16), default="cpc")  # cpc|manual


class ParkingCheck(Base):
    """各縣市路邊停車費欠費的最近一次查詢結果（每台車、每個縣市一筆，供待辦與自動檢查使用）。"""

    __tablename__ = "parking_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id", ondelete="CASCADE"), index=True)
    city: Mapped[str] = mapped_column(String(8))
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    total_amount: Mapped[float] = mapped_column(Float, default=0)
    payload: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(8), default="manual")  # manual|auto
