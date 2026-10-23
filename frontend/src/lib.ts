import type { ComplianceKind, EnergySource, EnergyType, ExpenseCategory, VehicleType } from "./api";

export const VEHICLE_TYPE_LABEL: Record<VehicleType, string> = {
  car: "汽車", scooter: "機車", heavy_moto: "重機",
};
export const ENERGY_TYPE_LABEL: Record<EnergyType, string> = {
  gasoline: "燃油", electric: "純電", hybrid: "油電",
};
export const SOURCE_LABEL: Record<EnergySource, string> = {
  gas_92: "92 無鉛", gas_95: "95 無鉛", gas_98: "98 無鉛", diesel: "柴油",
  home: "家用充電", public_ac: "公共慢充", public_dc: "公共快充", swap: "換電",
};
export const GAS_SOURCES: EnergySource[] = ["gas_92", "gas_95", "gas_98", "diesel"];
export const EV_SOURCES: EnergySource[] = ["home", "public_ac", "public_dc", "swap"];
export const SOURCES_BY_ENERGY: Record<EnergyType, EnergySource[]> = {
  gasoline: GAS_SOURCES,
  electric: EV_SOURCES,
  hybrid: [...GAS_SOURCES, ...EV_SOURCES],
};
export const isElectricSource = (s: EnergySource) => EV_SOURCES.includes(s);

export const COMPLIANCE_LABEL: Record<ComplianceKind, string> = {
  license_tax: "牌照稅", fuel_fee: "燃料使用費", compulsory_ins: "強制險", voluntary_ins: "任意險",
  inspection: "定期檢驗（驗車）", emission_test: "排氣檢驗", other: "其他",
};
export const EXPENSE_LABEL: Record<ExpenseCategory, string> = {
  parking: "停車費", toll: "過路費", energy_subscription: "電池／換電月租", wash: "洗車美容",
  accessory: "配件", other: "其他",
};
export const PRODUCT_LABEL: Record<string, string> = {
  gas_92: "92", gas_95: "95", gas_98: "98", diesel: "柴油",
};

export const today = () => {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};
export const nf = (n: number | null | undefined, digits = 0) =>
  n == null ? "—" : n.toLocaleString("zh-TW", { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const money = (n: number | null | undefined) => (n == null ? "—" : `$${nf(n)}`);
export const shortDate = (s: string) => s.slice(5).replace("-", "/");
export const vehicleName = (v: { brand: string; model: string; plate: string }) =>
  [v.brand, v.model].filter(Boolean).join(" ") || v.plate || "未命名車輛";
export const dt = (s: string | null | undefined) => (s ? s.replace("T", " ").slice(0, 16) : "—");
export const bytes = (n: number) =>
  n === 0 ? "0 B" : n > 1_048_576 ? `${(n / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
export const toNum = (s: string) => (s.trim() === "" || Number.isNaN(Number(s)) ? null : Number(s));

/** 常見加油站品牌；「其他」可自行輸入。中油以官方牌價為準，其餘品牌以中油牌價為參考。 */
export const STATION_BRANDS = ["中油", "台塑", "全國", "台亞", "福懋", "統一精工"] as const;
export const OTHER_STATION = "其他";
