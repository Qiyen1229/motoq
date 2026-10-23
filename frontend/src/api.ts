export type VehicleType = "car" | "scooter" | "heavy_moto";
export type EnergyType = "gasoline" | "electric" | "hybrid";
export type EnergySource =
  | "gas_92" | "gas_95" | "gas_98" | "diesel"
  | "home" | "public_ac" | "public_dc" | "swap";

export interface VehicleInput {
  vehicle_type: VehicleType;
  energy_type: EnergyType;
  brand: string;
  model: string;
  plate: string;
  displacement_cc: number | null;
  battery_kwh: number | null;
  default_energy_source: EnergySource | null;
  purchase_date: string | null;
  purchase_price: number | null;
  initial_odometer_km: number;
  status: "active" | "sold";
  sold_date: string | null;
  sold_price: number | null;
}
export interface Vehicle extends VehicleInput {
  id: number;
  current_odometer_km: number;
}
export interface Me {
  username: string;
  role: "admin" | "user";
  status: string;
}
export interface RegistrationStatus {
  has_users: boolean;
  mode: "closed" | "approval" | "open";
  can_register: boolean;
  needs_setup_token: boolean;
}
export interface EnergyLog {
  id: number;
  vehicle_id: number;
  log_date: string;
  odometer_km: number;
  total_km: number;
  quantity: number;
  unit: "L" | "kWh";
  unit_price: number;
  total_amount: number;
  is_full: boolean;
  missed_before: boolean;
  energy_source: EnergySource;
  station: string;
  start_soc: number | null;
  end_soc: number | null;
  note: string;
  efficiency: number | null;
  cost_per_km: number | null;
  distance_km: number | null;
}
export interface EnergyLogInput {
  log_date: string;
  odometer_km: number;
  quantity: number | null;
  unit_price: number | null;
  total_amount: number | null;
  is_full: boolean;
  missed_before: boolean;
  energy_source: EnergySource;
  station: string;
  start_soc: number | null;
  end_soc: number | null;
  note: string;
}
export interface NextMaintenance {
  name: string;
  state: MaintState;
  basis: "km" | "time" | null;
  due_date: string | null;
  remaining_km: number | null;
  remaining_days: number | null;
}
export interface Dashboard {
  vehicle: Vehicle;
  efficiency_unit: string;
  energy_unit: string;
  total_km: number;
  month_cost: number;
  month_energy: number;
  month_log_count: number;
  log_count: number;
  last_log_date: string | null;
  avg_efficiency: number | null;
  last_efficiency: number | null;
  cost_per_km: number | null;
  next_maintenance: NextMaintenance | null;
  warning: { active: boolean; recent_avg: number | null; baseline_avg: number | null; drop_pct: number | null };
}
export interface TrendPoint {
  start_date: string;
  end_date: string;
  distance_km: number;
  energy: number;
  cost: number;
  efficiency: number;
  cost_per_km: number;
  method: "full" | "soc";
}
export interface Defaults {
  energy_type: EnergyType;
  energy_source: EnergySource;
  unit_price: number | null;
  station: string;
  last_odometer_km: number;
  last_log_date: string | null;
  battery_kwh: number | null;
}
export interface Adjustment {
  id: number;
  vehicle_id: number;
  effective_date: string;
  offset_km: number;
  note: string;
}

export type MaintState = "ok" | "soon" | "overdue" | "unknown";
export interface MaintStatusItem {
  item_id: number;
  name: string;
  category: string;
  interval_km: number | null;
  interval_months: number | null;
  last_date: string | null;
  last_km: number | null;
  state: MaintState;
  basis: "km" | "time" | null;
  due_date: string | null;
  due_km: number | null;
  remaining_km: number | null;
  remaining_days: number | null;
  predicted_date_by_km: string | null;
  date_by_time: string | null;
  progress: number | null;
}
export interface MaintOverview {
  daily_km: number | null;
  current_km: number;
  items: MaintStatusItem[];
}
export interface MaintItem {
  id: number;
  vehicle_id: number;
  name: string;
  category: string;
  interval_km: number | null;
  interval_months: number | null;
  baseline_date: string | null;
  baseline_km: number | null;
  is_active: boolean;
  note: string;
}
export interface MaintItemInput {
  name: string;
  category: string;
  interval_km: number | null;
  interval_months: number | null;
  baseline_date: string | null;
  baseline_km: number | null;
  is_active: boolean;
  note: string;
}
export interface ServiceLine {
  id?: number;
  item_id: number | null;
  item_name?: string | null;
  description: string;
  part_name: string;
  cost: number;
}
export interface ServiceVisit {
  id: number;
  vehicle_id: number;
  visit_date: string;
  odometer_km: number;
  shop: string;
  total_cost: number;
  technician_note: string;
  attachment_count: number;
  lines: ServiceLine[];
}
export interface ServiceVisitInput {
  visit_date: string;
  odometer_km: number;
  shop: string;
  total_cost: number | null;
  technician_note: string;
  lines: Omit<ServiceLine, "id" | "item_name">[];
}

export type ComplianceKind =
  | "license_tax" | "fuel_fee" | "compulsory_ins" | "voluntary_ins" | "inspection" | "emission_test" | "other";
export interface Compliance {
  id: number;
  vehicle_id: number;
  kind: ComplianceKind;
  kind_label: string;
  due_date: string;
  amount: number;
  paid_date: string | null;
  provider: string;
  policy_no: string;
  recurrence_months: number | null;
  note: string;
  state: "paid" | "overdue" | "due_soon" | "ok";
  days_left: number;
  level: number;
  vehicle?: string;
}
export interface ComplianceInput {
  kind: ComplianceKind;
  due_date: string;
  amount: number;
  paid_date: string | null;
  provider: string;
  policy_no: string;
  recurrence_months: number | null;
  note: string;
}
export interface Fine {
  id: number;
  vehicle_id: number;
  fine_no: string;
  violation_date: string;
  violation: string;
  location: string;
  amount: number;
  due_date: string | null;
  paid_date: string | null;
  source: string;
  overdue: boolean;
}
export interface FineInput {
  fine_no: string;
  violation_date: string;
  violation: string;
  location: string;
  amount: number;
  due_date: string | null;
  paid_date: string | null;
}
export type ExpenseCategory = "parking" | "toll" | "energy_subscription" | "wash" | "accessory" | "other";
export interface Expense {
  id: number;
  vehicle_id: number;
  expense_date: string;
  category: ExpenseCategory;
  amount: number;
  note: string;
}
export interface ExpenseInput {
  expense_date: string;
  category: ExpenseCategory;
  amount: number;
  note: string;
}
export interface EtagEntry {
  id: number;
  entry_date: string;
  kind: "topup" | "toll" | "balance_adjust";
  amount: number;
  note: string;
}
export interface PriceSuggestion {
  price: number | null;
  basis: "last_at_station" | "cpc_reference" | "last_same_source" | null;
  as_of: string | null;
  note: string;
}
export interface ParkingBill {
  bill_no: string;
  parking_date: string;
  pay_limit_date: string;
  status: number | null;
  hours: number | null;
  amount: number;
  pay_amount: number;
}
export interface ParkingReminder {
  reminder_no: string;
  limit_date: string;
  amount: number;
  extra_charge: number;
  pay_amount: number;
  prosecuted: boolean;
  prosecute_limit_date: string;
  bills: ParkingBill[];
}
export interface ParkingCity {
  code: string;
  name: string;
  insecure: boolean;
  pay_url: string;
}
export interface ParkingCheck {
  city_code: string;
  city: string;
  checked_at: string;
  total_count: number;
  total_amount: number;
  source: "manual" | "auto";
}
export interface LicenseTaxEstimate {
  license_tax: { amount: number | null; exempt: boolean; note: string; due_date: string; already_created: boolean };
  fuel_fee: { amount: number | null; note: string };
}
export interface ParkingResult {
  city_code: string;
  insecure: boolean;
  plate: string;
  car_type: "C" | "M" | "O";
  car_type_label: string;
  city: string;
  total_count: number;
  total_amount: number;
  bills: ParkingBill[];
  reminders: ParkingReminder[];
  update_time: string;
  pay_url: string;
  cached: boolean;
}
export interface Attachment {
  id: number;
  owner_type: string;
  owner_id: number;
  original_name: string;
  size_bytes: number;
  url: string;
  thumb_url: string;
}
export interface AttentionItem {
  vehicle_id: number;
  vehicle: string;
  kind: "maintenance" | "compliance" | "fine" | "efficiency" | "parking" | "etag";
  severity: "critical" | "warning" | "info";
  title: string;
  detail: string;
  link: string;
}
export interface FuelPrice {
  product: "gas_92" | "gas_95" | "gas_98" | "diesel";
  price: number;
  price_date: string;
  change: number | null;
  source: string;
}
export interface PeriodReport {
  vehicle_id: number;
  vehicle?: string;
  year?: number;
  start: string;
  end: string;
  days: number;
  distance_km: number;
  total_cost: number;
  cost_per_km: number | null;
  categories: { key: string; label: string; amount: number }[];
  monthly: { month: string; amount: number }[];
  avg_efficiency: number | null;
  efficiency_unit: string;
  energy_cost_per_km: number | null;
}
export interface UserSettings {
  anomaly_drop_pct: number;
  lead_days: number[];
  parking_cities: string[];
  parking_auto_check: boolean;
  etag_low_balance: number;
}
export interface GlobalSettings {
  registration_mode: "closed" | "approval" | "open";
  session_days: number;
  login_max_failures: number;
  login_window_seconds: number;
}
export interface AdminOverview {
  version: string;
  users: { total: number; active?: number; pending?: number; disabled?: number };
  vehicles: number;
  energy_logs: number;
  attachments: number;
  active_sessions: number;
  failed_logins_24h: number;
  db_bytes: number;
  uploads_bytes: number;
  cookie_secure: boolean;
  setup_token_configured: boolean;
  settings: GlobalSettings;
}
export interface AdminUser {
  id: number;
  username: string;
  role: "admin" | "user";
  status: "active" | "pending" | "disabled";
  created_at: string;
  last_login_at: string | null;
  vehicle_count: number;
  session_count: number;
}
export interface SecurityEvent {
  id: number;
  kind: string;
  success: boolean;
  username: string;
  ip: string;
  user_agent: string;
  detail: string;
  created_at: string;
}
export interface AdminSession {
  id: number;
  username: string;
  ip: string;
  user_agent: string;
  created_at: string;
  last_seen_at: string | null;
  expires_at: string;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown, message: string) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const res = await fetch(`/api/v1${path}`, {
    method,
    credentials: "same-origin",
    headers: isForm || body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const d = data?.detail;
    const msg =
      typeof d === "string" ? d : d?.message ?? (Array.isArray(d) ? d[0]?.msg ?? "輸入資料有誤，請檢查欄位" : `錯誤 ${res.status}`);
    throw new ApiError(res.status, d, msg);
  }
  return data as T;
}
const get = <T>(p: string) => request<T>("GET", p);
const post = <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {});
const put = <T>(p: string, b: unknown) => request<T>("PUT", p, b);
const del = (p: string) => request<void>("DELETE", p);

export const api = {
  // auth
  me: () => get<Me>("/auth/me"),
  registration: () => get<RegistrationStatus>("/auth/registration"),
  login: (username: string, password: string) => post<Me>("/auth/login", { username, password }),
  register: (username: string, password: string, setup_token?: string) =>
    post<Me & { pending: boolean }>("/auth/register", { username, password, setup_token: setup_token || null }),
  logout: () => post("/auth/logout"),
  changePassword: (current_password: string, new_password: string) =>
    post("/auth/change-password", { current_password, new_password }),

  // vehicles
  vehicles: () => get<Vehicle[]>("/vehicles"),
  createVehicle: (v: VehicleInput) => post<Vehicle>("/vehicles", v),
  updateVehicle: (id: number, v: VehicleInput) => put<Vehicle>(`/vehicles/${id}`, v),
  deleteVehicle: (id: number) => del(`/vehicles/${id}`),
  adjustments: (id: number) => get<Adjustment[]>(`/vehicles/${id}/odometer-adjustments`),
  addAdjustment: (id: number, a: { effective_date: string; offset_km: number; note: string }) =>
    post<Adjustment>(`/vehicles/${id}/odometer-adjustments`, a),
  deleteAdjustment: (id: number) => del(`/odometer-adjustments/${id}`),

  // energy
  logs: (vid: number, limit?: number) =>
    get<EnergyLog[]>(`/vehicles/${vid}/energy-logs${limit ? `?limit=${limit}` : ""}`),
  defaults: (vid: number) => get<Defaults>(`/vehicles/${vid}/energy-logs/defaults`),
  createLog: (vid: number, b: EnergyLogInput, force = false) =>
    post<EnergyLog>(`/vehicles/${vid}/energy-logs${force ? "?force=true" : ""}`, b),
  updateLog: (id: number, b: EnergyLogInput, force = false) =>
    put<EnergyLog>(`/energy-logs/${id}${force ? "?force=true" : ""}`, b),
  deleteLog: (id: number) => del(`/energy-logs/${id}`),
  priceSuggestion: (vid: number, energy_source: string, station: string) =>
    get<PriceSuggestion>(
      `/vehicles/${vid}/energy-logs/price-suggestion?energy_source=${energy_source}&station=${encodeURIComponent(station)}`),
  dashboard: (vid: number) => get<Dashboard>(`/vehicles/${vid}/dashboard`),
  trend: (vid: number) => get<TrendPoint[]>(`/vehicles/${vid}/efficiency/trend`),
  attention: () => get<AttentionItem[]>("/attention"),
  fuelLatest: () => get<FuelPrice[]>("/fuel-prices/latest"),

  // maintenance
  maintStatus: (vid: number) => get<MaintOverview>(`/vehicles/${vid}/maintenance/status`),
  maintItems: (vid: number) => get<MaintItem[]>(`/vehicles/${vid}/maintenance-items`),
  applyTemplate: (vid: number, b: { baseline_date: string | null; baseline_km: number | null }) =>
    post<{ created: number; skipped: number }>(`/vehicles/${vid}/maintenance-items/apply-template`, b),
  createItem: (vid: number, b: MaintItemInput) => post<MaintItem>(`/vehicles/${vid}/maintenance-items`, b),
  updateItem: (id: number, b: MaintItemInput) => put<MaintItem>(`/maintenance-items/${id}`, b),
  deleteItem: (id: number) => del(`/maintenance-items/${id}`),
  visits: (vid: number) => get<ServiceVisit[]>(`/vehicles/${vid}/service-visits`),
  createVisit: (vid: number, b: ServiceVisitInput) => post<ServiceVisit>(`/vehicles/${vid}/service-visits`, b),
  updateVisit: (id: number, b: ServiceVisitInput) => put<ServiceVisit>(`/service-visits/${id}`, b),
  deleteVisit: (id: number) => del(`/service-visits/${id}`),

  // compliance / fines / expenses / etag
  compliance: (vid: number) => get<Compliance[]>(`/vehicles/${vid}/compliance`),
  createCompliance: (vid: number, b: ComplianceInput) => post<Compliance>(`/vehicles/${vid}/compliance`, b),
  updateCompliance: (id: number, b: ComplianceInput) => put<Compliance>(`/compliance/${id}`, b),
  deleteCompliance: (id: number) => del(`/compliance/${id}`),
  payCompliance: (id: number, b: { paid_date?: string; amount?: number; create_next: boolean }) =>
    post<{ paid: number; next_id: number | null }>(`/compliance/${id}/pay`, b),
  fines: (vid: number) => get<Fine[]>(`/vehicles/${vid}/fines`),
  createFine: (vid: number, b: FineInput) => post<Fine>(`/vehicles/${vid}/fines`, b),
  updateFine: (id: number, b: FineInput) => put<Fine>(`/fines/${id}`, b),
  deleteFine: (id: number) => del(`/fines/${id}`),
  importFines: (vid: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ added: number; skipped: number }>("POST", `/vehicles/${vid}/fines/import`, fd);
  },
  lookupFines: (vid: number) =>
    post<{ provider: string; demo: boolean; results: (FineInput & { source: string })[] }>(
      `/vehicles/${vid}/fines/lookup`),
  expenses: (vid: number) => get<Expense[]>(`/vehicles/${vid}/expenses`),
  createExpense: (vid: number, b: ExpenseInput) => post<Expense>(`/vehicles/${vid}/expenses`, b),
  deleteExpense: (id: number) => del(`/expenses/${id}`),
  etag: (vid: number) => get<{ balance: number; entries: EtagEntry[] }>(`/vehicles/${vid}/etag`),
  createEtag: (vid: number, b: Omit<EtagEntry, "id">) => post(`/vehicles/${vid}/etag`, b),
  deleteEtag: (id: number) => del(`/etag/${id}`),

  // parking
  parkingCities: () => get<ParkingCity[]>("/parking/cities"),
  parkingLookup: (plate: string, car_type: string, city: string, vehicle_id?: number) =>
    post<ParkingResult>("/parking/lookup", { plate, car_type, city, vehicle_id: vehicle_id ?? null }),
  parkingChecks: (vid: number) => get<ParkingCheck[]>(`/vehicles/${vid}/parking-checks`),
  complianceEstimate: (vid: number) => get<LicenseTaxEstimate>(`/vehicles/${vid}/compliance/estimate`),

  // attachments
  attachments: (owner_type: string, owner_id: number) =>
    get<Attachment[]>(`/attachments?owner_type=${owner_type}&owner_id=${owner_id}`),
  uploadAttachment: (owner_type: string, owner_id: number, file: File) => {
    const fd = new FormData();
    fd.append("owner_type", owner_type);
    fd.append("owner_id", String(owner_id));
    fd.append("file", file);
    return request<Attachment>("POST", "/attachments", fd);
  },
  deleteAttachment: (id: number) => del(`/attachments/${id}`),

  // reports
  annual: (vid: number, year: number) => get<PeriodReport>(`/vehicles/${vid}/reports/annual?year=${year}`),
  saveAnnual: (vid: number, year: number) => post(`/vehicles/${vid}/reports/annual?year=${year}`),
  savedAnnual: (vid: number) =>
    get<{ id: number; year: number; trigger: string; generated_at: string }[]>(`/vehicles/${vid}/reports/annual/saved`),
  compare: (ids: number[], from: string, to: string) =>
    get<PeriodReport[]>(`/reports/compare?vehicle_ids=${ids.join(",")}&from=${from}&to=${to}`),

  // settings & data
  settings: () => get<UserSettings>("/settings"),
  saveSettings: (s: Partial<UserSettings>) => put<UserSettings>("/settings", s),
  importData: (file: File, dryRun: boolean) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ dry_run: boolean; counts: Record<string, number>; snapshot?: string }>(
      "POST", `/data/import?dry_run=${dryRun}`, fd);
  },

  // admin
  adminOverview: () => get<AdminOverview>("/admin/overview"),
  adminUsers: () => get<AdminUser[]>("/admin/users"),
  adminPatchUser: (id: number, b: { role?: string; status?: string }) =>
    request("PATCH", `/admin/users/${id}`, b),
  adminResetPassword: (id: number, new_password: string) => post(`/admin/users/${id}/reset-password`, { new_password }),
  adminDeleteUser: (id: number) => del(`/admin/users/${id}`),
  adminEvents: (kind?: string) => get<SecurityEvent[]>(`/admin/events?limit=150${kind ? `&kind=${kind}` : ""}`),
  adminSessions: () => get<AdminSession[]>("/admin/sessions"),
  adminRevokeSession: (id: number) => del(`/admin/sessions/${id}`),
  adminSaveSettings: (b: Partial<GlobalSettings>) => put<GlobalSettings>("/admin/settings", b),
  refreshFuel: () => post<{ updated: number }>("/fuel-prices/refresh"),
  setFuelPrice: (b: { price_date: string; product: string; price: number }) => post("/fuel-prices", b),
};
