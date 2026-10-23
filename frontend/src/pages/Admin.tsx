import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type AdminUser, type GlobalSettings } from "../api";
import { Chip, ConfirmButton, ErrorText, Field, PageTitle, Stat, Tabs } from "../components/ui";
import { bytes, dt, nf } from "../lib";

type Tab = "overview" | "users" | "events" | "sessions" | "security";

export default function Admin() {
  const [tab, setTab] = useState<Tab>("overview");
  return (
    <div className="space-y-4">
      <PageTitle>管理後台</PageTitle>
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[
        { id: "overview", label: "概覽" }, { id: "users", label: "使用者" }, { id: "events", label: "紀錄" },
        { id: "sessions", label: "登入中" }, { id: "security", label: "安全" },
      ]} />
      {tab === "overview" && <Overview />}
      {tab === "users" && <Users />}
      {tab === "events" && <Events />}
      {tab === "sessions" && <Sessions />}
      {tab === "security" && <Security />}
    </div>
  );
}

function Overview() {
  const q = useQuery({ queryKey: ["adminOverview"], queryFn: api.adminOverview });
  const o = q.data;
  if (!o) return <p className="text-center text-slate-500">載入中…</p>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Stat label="使用者" value={nf(o.users.total)} sub={`啟用 ${o.users.active ?? 0}・待核准 ${o.users.pending ?? 0}・停用 ${o.users.disabled ?? 0}`} />
        <Stat label="登入中工作階段" value={nf(o.active_sessions)} />
        <Stat label="24 小時登入失敗" value={nf(o.failed_logins_24h)} tone={o.failed_logins_24h >= 10 ? "warn" : undefined} />
        <Stat label="車輛／加油記錄" value={`${nf(o.vehicles)} / ${nf(o.energy_logs)}`} />
        <Stat label="資料庫" value={bytes(o.db_bytes)} />
        <Stat label="附件" value={bytes(o.uploads_bytes)} sub={`${o.attachments} 張`} />
      </div>
      <section className="card space-y-2">
        <h2 className="text-base font-semibold">部署安全檢查</h2>
        <Check ok={o.cookie_secure} label="Cookie 已設為 Secure（僅 HTTPS 傳送）" hint="公網部署請設定 MOTOQ_COOKIE_SECURE=true" />
        <Check ok={o.settings.registration_mode === "closed"} label={`註冊模式：${MODE_LABEL[o.settings.registration_mode]}`} hint="不需要時建議保持關閉" />
        <Check ok={o.setup_token_configured || o.users.total > 0} label="初始設定碼" hint="首次部署前可設定 MOTOQ_SETUP_TOKEN，避免他人搶先註冊成為管理員" />
      </section>
      <p className="text-center text-xs text-slate-500">MotoQ {o.version}</p>
    </div>
  );
}

function Check({ ok, label, hint }: { ok: boolean; label: string; hint?: string }) {
  return (
    <div className="flex items-start gap-3 text-sm">
      <span className={`mt-0.5 ${ok ? "text-emerald-500" : "text-amber-500"}`}>{ok ? "●" : "▲"}</span>
      <div>
        <div>{label}</div>
        {!ok && hint && <div className="text-xs text-slate-500">{hint}</div>}
      </div>
    </div>
  );
}

const MODE_LABEL = { closed: "關閉", approval: "需管理員核准", open: "開放" } as const;
const ROLE_TONE = { admin: "gold", user: "gray" } as const;
const STATUS_TONE = { active: "green", pending: "amber", disabled: "red" } as const;
const STATUS_LABEL = { active: "啟用", pending: "待核准", disabled: "停用" } as const;

function Users() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["adminUsers"], queryFn: api.adminUsers });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["adminUsers"] }); qc.invalidateQueries({ queryKey: ["adminOverview"] }); };
  const patch = useMutation({ mutationFn: (v: { id: number; role?: string; status?: string }) => api.adminPatchUser(v.id, v), onSuccess: refresh });
  const del = useMutation({ mutationFn: (id: number) => api.adminDeleteUser(id), onSuccess: refresh });
  const [pwFor, setPwFor] = useState<number | null>(null);
  const [pw, setPw] = useState("");
  const reset = useMutation({ mutationFn: () => api.adminResetPassword(pwFor!, pw), onSuccess: () => { setPwFor(null); setPw(""); } });

  const card = (u: AdminUser) => (
    <li key={u.id} className="card space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold">{u.username}</div>
          <div className="text-xs text-slate-500">
            {u.vehicle_count} 台車・{u.session_count} 個登入中・最後登入 {dt(u.last_login_at)}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Chip tone={ROLE_TONE[u.role]}>{u.role === "admin" ? "管理員" : "使用者"}</Chip>
          <Chip tone={STATUS_TONE[u.status]}>{STATUS_LABEL[u.status]}</Chip>
        </div>
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        {u.status === "pending" && <button className="btn-primary btn-sm" onClick={() => patch.mutate({ id: u.id, status: "active" })}>核准</button>}
        {u.status === "active" && <button className="btn-ghost btn-sm" onClick={() => patch.mutate({ id: u.id, status: "disabled" })}>停用</button>}
        {u.status === "disabled" && <button className="btn-ghost btn-sm" onClick={() => patch.mutate({ id: u.id, status: "active" })}>啟用</button>}
        {u.role === "user" && u.status === "active" && <button className="btn-ghost btn-sm" onClick={() => patch.mutate({ id: u.id, role: "admin" })}>設為管理員</button>}
        {u.role === "admin" && <button className="btn-ghost btn-sm" onClick={() => patch.mutate({ id: u.id, role: "user" })}>取消管理員</button>}
        <button className="btn-ghost btn-sm" onClick={() => setPwFor(pwFor === u.id ? null : u.id)}>重設密碼</button>
        <ConfirmButton onConfirm={() => del.mutate(u.id)} confirmLabel="確認刪除（含所有資料）">刪除</ConfirmButton>
      </div>
      {pwFor === u.id && (
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); reset.mutate(); }}>
          <Field label="新密碼（至少 8 碼）">
            <input className="input" type="text" autoComplete="off" value={pw} onChange={(e) => setPw(e.target.value)} />
          </Field>
          <button className="btn-primary w-full" disabled={pw.length < 8 || reset.isPending}>設定並登出該使用者所有裝置</button>
        </form>
      )}
    </li>
  );

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">管理員可管理帳號，但看不到其他使用者的車輛與記錄內容。</p>
      <ErrorText error={patch.error ?? del.error ?? reset.error} />
      <ul className="space-y-2">{q.data?.map(card)}</ul>
    </div>
  );
}

const KIND_LABEL: Record<string, string> = {
  login: "登入", register: "註冊", parking_lookup: "停車費查詢", password_change: "變更密碼", data_import: "資料匯入",
  admin_user_update: "管理：使用者異動", admin_reset_password: "管理：重設密碼", admin_delete_user: "管理：刪除使用者",
  admin_revoke_session: "管理：登出工作階段", admin_settings: "管理：安全設定", admin_fuel_price: "管理：油價",
};

function Events() {
  const [kind, setKind] = useState("");
  const q = useQuery({ queryKey: ["adminEvents", kind], queryFn: () => api.adminEvents(kind || undefined) });
  return (
    <div className="space-y-3">
      <select className="input" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="事件類型">
        <option value="">全部事件</option>
        {Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
      <ul className="space-y-2">
        {q.data?.map((e) => (
          <li key={e.id} className="card !p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{KIND_LABEL[e.kind] ?? e.kind}{e.username && `・${e.username}`}</span>
              <Chip tone={e.success ? "green" : "red"}>{e.success ? "成功" : "失敗"}</Chip>
            </div>
            <div className="mt-1 text-xs text-slate-500">{dt(e.created_at)}・{e.ip || "—"}{e.detail && `・${e.detail}`}</div>
          </li>
        ))}
        {q.data?.length === 0 && <li className="text-center text-sm text-slate-500">沒有符合的紀錄</li>}
      </ul>
    </div>
  );
}

function Sessions() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["adminSessions"], queryFn: api.adminSessions });
  const revoke = useMutation({ mutationFn: (id: number) => api.adminRevokeSession(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["adminSessions"] }) });
  return (
    <div className="space-y-2">
      <ErrorText error={revoke.error} />
      <ul className="space-y-2">
        {q.data?.map((s) => (
          <li key={s.id} className="card flex items-start justify-between gap-3 !p-3">
            <div className="min-w-0 text-sm">
              <div className="font-medium">{s.username}</div>
              <div className="text-xs text-slate-500">{s.ip}・最近活動 {dt(s.last_seen_at)}</div>
              <div className="truncate text-xs text-slate-500">{s.user_agent}</div>
            </div>
            <ConfirmButton onConfirm={() => revoke.mutate(s.id)} confirmLabel="登出？">登出</ConfirmButton>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Security() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["adminSettings"], queryFn: async () => (await api.adminOverview()).settings });
  const [draft, setDraft] = useState<Partial<GlobalSettings>>({});
  const s = { ...q.data, ...draft } as GlobalSettings | undefined;
  const save = useMutation({
    mutationFn: () => api.adminSaveSettings(draft),
    onSuccess: () => { setDraft({}); qc.invalidateQueries({ queryKey: ["adminSettings"] }); qc.invalidateQueries({ queryKey: ["adminOverview"] }); },
  });
  const [price, setPrice] = useState({ product: "gas_95", price: "" });
  const refreshFuel = useMutation({ mutationFn: api.refreshFuel, onSuccess: () => qc.invalidateQueries({ queryKey: ["fuel"] }) });
  const setFuel = useMutation({
    mutationFn: () => api.setFuelPrice({ price_date: new Date().toISOString().slice(0, 10), product: price.product, price: Number(price.price) }),
    onSuccess: () => { setPrice({ ...price, price: "" }); qc.invalidateQueries({ queryKey: ["fuel"] }); },
  });
  if (!s) return <p className="text-center text-slate-500">載入中…</p>;

  return (
    <div className="space-y-4">
      <section className="card space-y-3">
        <h2 className="text-base font-semibold">註冊與登入</h2>
        <Field label="註冊模式">
          <select className="input" value={s.registration_mode} onChange={(e) => setDraft({ ...draft, registration_mode: e.target.value as GlobalSettings["registration_mode"] })}>
            <option value="closed">關閉（只有管理員可新增使用者）</option>
            <option value="approval">開放註冊，需管理員核准</option>
            <option value="open">開放註冊，立即啟用（不建議公網使用）</option>
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="登入有效天數"><input className="input" inputMode="numeric" value={s.session_days} onChange={(e) => setDraft({ ...draft, session_days: Number(e.target.value) || 1 })} /></Field>
          <Field label="失敗上限（次）"><input className="input" inputMode="numeric" value={s.login_max_failures} onChange={(e) => setDraft({ ...draft, login_max_failures: Number(e.target.value) || 5 })} /></Field>
          <Field label="限流視窗（秒）" className="col-span-2"><input className="input" inputMode="numeric" value={s.login_window_seconds} onChange={(e) => setDraft({ ...draft, login_window_seconds: Number(e.target.value) || 600 })} /></Field>
        </div>
        <ErrorText error={save.error} />
        <button className="btn-primary w-full" disabled={save.isPending || Object.keys(draft).length === 0}
          onClick={() => save.mutate()}>
          {save.isSuccess && Object.keys(draft).length === 0 ? "已儲存 ✓" : "儲存安全設定"}
        </button>
      </section>

      <section className="card space-y-3">
        <h2 className="text-base font-semibold">中油牌價</h2>
        <p className="text-xs text-slate-500">系統每天自動抓取；若來源無法連線，可在此手動輸入今天的牌價。</p>
        <button className="btn-ghost w-full" disabled={refreshFuel.isPending} onClick={() => refreshFuel.mutate()}>
          {refreshFuel.isSuccess ? `已更新 ${refreshFuel.data?.updated} 項 ✓` : "立即更新"}
        </button>
        <ErrorText error={refreshFuel.error} />
        <div className="grid grid-cols-3 gap-2">
          <select className="input" value={price.product} onChange={(e) => setPrice({ ...price, product: e.target.value })}>
            <option value="gas_92">92</option><option value="gas_95">95</option><option value="gas_98">98</option><option value="diesel">柴油</option>
          </select>
          <input className="input" inputMode="decimal" placeholder="牌價" value={price.price} onChange={(e) => setPrice({ ...price, price: e.target.value })} />
          <button className="btn-ghost" disabled={!price.price || setFuel.isPending} onClick={() => setFuel.mutate()}>輸入</button>
        </div>
        <ErrorText error={setFuel.error} />
      </section>
    </div>
  );
}
