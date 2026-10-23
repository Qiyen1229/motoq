import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

VehicleType = Literal["car", "scooter", "heavy_moto"]
EnergyType = Literal["gasoline", "electric", "hybrid"]
EnergySource = Literal["gas_92", "gas_95", "gas_98", "diesel", "home", "public_ac", "public_dc", "swap"]

GASOLINE_SOURCES = {"gas_92", "gas_95", "gas_98", "diesel"}
ELECTRIC_SOURCES = {"home", "public_ac", "public_dc", "swap"}


def unit_for(source: str) -> str:
    return "L" if source in GASOLINE_SOURCES else "kWh"


def allowed_sources(energy_type: str) -> set[str]:
    if energy_type == "gasoline":
        return GASOLINE_SOURCES
    if energy_type == "electric":
        return ELECTRIC_SOURCES
    return GASOLINE_SOURCES | ELECTRIC_SOURCES


USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str
    password: str = Field(min_length=8, max_length=128)
    setup_token: str | None = None

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        v = v.strip()
        if not USERNAME_RE.match(v):
            raise ValueError("帳號需為 3–32 字元，僅限英數與 _ . -")
        return v


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class VehicleIn(BaseModel):
    vehicle_type: VehicleType
    energy_type: EnergyType = "gasoline"
    brand: str = ""
    model: str = ""
    plate: str = ""
    displacement_cc: int | None = Field(None, ge=0)
    battery_kwh: float | None = Field(None, gt=0)
    default_energy_source: EnergySource | None = None
    purchase_date: date | None = None
    purchase_price: int | None = Field(None, ge=0)
    initial_odometer_km: int = Field(0, ge=0)
    status: Literal["active", "sold"] = "active"
    sold_date: date | None = None
    sold_price: int | None = Field(None, ge=0)


class VehicleOut(VehicleIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    current_odometer_km: int = 0


class AdjustmentIn(BaseModel):
    effective_date: date
    offset_km: int
    note: str = ""


class AdjustmentOut(AdjustmentIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    vehicle_id: int


class EnergyLogIn(BaseModel):
    log_date: date
    odometer_km: int = Field(ge=0)
    quantity: float | None = Field(None, gt=0)
    unit_price: float | None = Field(None, ge=0)
    total_amount: int | None = Field(None, ge=0)
    is_full: bool = True
    missed_before: bool = False
    energy_source: EnergySource
    station: str = ""
    start_soc: int | None = Field(None, ge=0, le=100)
    end_soc: int | None = Field(None, ge=0, le=100)
    note: str = ""


class EnergyLogOut(BaseModel):
    id: int
    vehicle_id: int
    log_date: date
    odometer_km: int
    total_km: int
    quantity: float
    unit: str
    unit_price: float
    total_amount: int
    is_full: bool
    missed_before: bool
    energy_source: str
    station: str
    start_soc: int | None
    end_soc: int | None
    note: str
    efficiency: float | None = None
    cost_per_km: float | None = None
    distance_km: int | None = None


class UserSettingsIn(BaseModel):
    anomaly_drop_pct: float | None = Field(None, ge=1, le=80)
    lead_days: list[int] | None = None
    parking_cities: list[str] | None = None
    parking_auto_check: bool | None = None
    etag_low_balance: int | None = Field(None, ge=0, le=100000)

    @field_validator("parking_cities")
    @classmethod
    def _cities(cls, v):
        if v is None:
            return v
        from app.services.parking import CITIES

        if len(v) > len(CITIES) or any(c not in CITIES for c in v):
            raise ValueError("縣市代碼不正確")
        return list(dict.fromkeys(v))

    @field_validator("lead_days")
    @classmethod
    def _lead(cls, v):
        if v is None:
            return v
        if not v or len(v) > 6 or any(d < 0 or d > 365 for d in v):
            raise ValueError("提前天數需為 0–365 的 1–6 個數字")
        return sorted(set(v), reverse=True)


class GlobalSettingsIn(BaseModel):
    registration_mode: Literal["closed", "approval", "open"] | None = None
    session_days: int | None = Field(None, ge=1, le=365)
    login_max_failures: int | None = Field(None, ge=3, le=50)
    login_window_seconds: int | None = Field(None, ge=60, le=86400)


# ───── 保養 ─────
class MaintenanceItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    category: str = "其他"
    interval_km: int | None = Field(None, gt=0)
    interval_months: int | None = Field(None, gt=0)
    baseline_date: date | None = None
    baseline_km: int | None = Field(None, ge=0)
    is_active: bool = True
    note: str = ""


class ServiceLineIn(BaseModel):
    item_id: int | None = None
    description: str = ""
    part_name: str = ""
    cost: int = Field(0, ge=0)


class ServiceVisitIn(BaseModel):
    visit_date: date
    odometer_km: int = Field(ge=0)
    shop: str = ""
    total_cost: int | None = Field(None, ge=0)  # 省略時以明細加總
    technician_note: str = ""
    lines: list[ServiceLineIn] = []


# ───── 稅費、罰單、其他 ─────
ComplianceKind = Literal["license_tax", "fuel_fee", "compulsory_ins", "voluntary_ins", "inspection", "emission_test", "other"]


class ComplianceIn(BaseModel):
    kind: ComplianceKind
    due_date: date
    amount: int = Field(0, ge=0)
    paid_date: date | None = None
    provider: str = ""
    policy_no: str = ""
    recurrence_months: int | None = Field(None, gt=0, le=120)
    note: str = ""


class PayIn(BaseModel):
    paid_date: date | None = None
    amount: int | None = Field(None, ge=0)
    create_next: bool = True


class FineIn(BaseModel):
    fine_no: str = ""
    violation_date: date
    violation: str = ""
    location: str = ""
    amount: int = Field(0, ge=0)
    due_date: date | None = None
    paid_date: date | None = None


class ExpenseIn(BaseModel):
    expense_date: date
    category: Literal["parking", "toll", "energy_subscription", "wash", "accessory", "other"]
    amount: int = Field(ge=0)
    note: str = ""


class EtagIn(BaseModel):
    entry_date: date
    kind: Literal["topup", "toll", "balance_adjust"]
    amount: int
    note: str = ""


class FuelPriceIn(BaseModel):
    price_date: date
    product: Literal["gas_92", "gas_95", "gas_98", "diesel"]
    price: float = Field(gt=0, lt=1000)
