import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type ExpenseCategory, type ParkingBill, type ParkingResult, type VehicleType } from "../api";
import OfficialLinks from "../components/OfficialLinks";
import Attachments from "../components/Attachments";
import Icon from "../components/Icon";
import { Chip, ConfirmButton, Empty, ErrorText, Field, PageTitle, Tabs } from "../components/ui";
import { EXPENSE_LABEL, money, nf, today, toNum } from "../lib";
import { useVehicle } from "../vehicleContext";
import { Link } from "react-router-dom";

type Tab = "fines" | "parking" | "expenses" | "etag" | "compliance";

export default function Expenses() {
  const { vehicle } = useVehicle();
  const [sp] = useSearchParams();
  const initial = (["fines", "parking", "expenses", "etag", "compliance"] as Tab[]).find((t) => t === sp.get("tab"));
  const [tab, setTab] = useState<Tab>(initial ?? "fines");
  if (!vehicle) return <Empty>請先新增車輛</Empty>;
  return (
    <div className="space-y-4">
      <PageTitle>費用</PageTitle>
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[
        { id: "fines", label: "罰單" }, { id: "parking", label: "停車費" }, { id: "expenses", label: "支出" },
        { id: "etag", label: "etag" }, { id: "compliance", label: "稅費" },
      ]} />
      {tab === "fines" && <Fines vid={vehicle.id} />}
      {tab === "parking" && <ParkingLookup vehicleId={vehicle.id} plate={vehicle.plate} vehicleType={vehicle.vehicle_type} />}
      {tab === "expenses" && <Expenses_ vid={vehicle.id} />}
      {tab === "etag" && <Etag vid={vehicle.id} />}
      {tab === "compliance" && (
        <Link to="/compliance" className="card block text-center">
          <div className="font-semibold">前往「稅費與到期」</div>
          <div className="text-xs text-slate-500">牌照稅、燃料費、強制險、任意險、驗車與排氣檢驗</div>
        </Link>
      )}
    </div>
  );
}

function Fines({ vid }: { vid: number }) {
  // 違規罰單目前沒有「只憑車牌就能查」的官方開放 API（需身分證字號＋驗證碼）→ 提供官方入口與 CSV 匯入
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["fines", vid], queryFn: () => api.fines(vid) });
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const [form, setForm] = useState({ violation_date: today(), violation: "", location: "", amount: "", fine_no: "", due_date: "" });
  const file = useRef<HTMLInputElement>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["fines"] }); qc.invalidateQueries({ queryKey: ["attention"] }); };

  const create = useMutation({
    mutationFn: () => api.createFine(vid, {
      fine_no: form.fine_no.trim(), violation_date: form.violation_date, violation: form.violation.trim(),
      location: form.location.trim(), amount: toNum(form.amount) ?? 0, due_date: form.due_date || null, paid_date: null,
    }),
    onSuccess: () => { setAdding(false); refresh(); },
  });
  const markPaid = useMutation({
    mutationFn: (f: { id: number } & Record<string, unknown>) => api.updateFine(f.id, {
      fine_no: f.fine_no as string, violation_date: f.violation_date as string, violation: f.violation as string,
      location: f.location as string, amount: f.amount as number, due_date: f.due_date as string | null, paid_date: today(),
    }),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: (id: number) => api.deleteFine(id), onSuccess: refresh });
  const importCsv = useMutation({ mutationFn: (f: File) => api.importFines(vid, f), onSuccess: refresh });
  const lookup = useMutation({ mutationFn: () => api.lookupFines(vid) });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary btn-sm" onClick={() => setAdding(!adding)}>{adding ? "取消" : "＋ 新增罰單"}</button>
        <button className="btn-ghost btn-sm" onClick={() => file.current?.click()}>匯入 CSV</button>
        <button className="btn-ghost btn-sm" onClick={() => lookup.mutate()} disabled={lookup.isPending}>查詢未繳罰單</button>
        <input ref={file} type="file" accept=".csv,text/csv" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) importCsv.mutate(f); e.target.value = ""; }} />
      </div>
      <ErrorText error={importCsv.error ?? remove.error ?? lookup.error ?? markPaid.error} />
      {importCsv.data && <p className="text-sm gold-text">匯入完成：新增 {importCsv.data.added} 筆，略過重複 {importCsv.data.skipped} 筆。</p>}
      {lookup.data && (
        <div className="card space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">查詢結果</span>
            {lookup.data.demo && <Chip tone="amber">示範資料</Chip>}
          </div>
          <p className="text-xs text-slate-500">
            官方資料源尚未串接，目前為預留介面的示範結果。實際罰單請用「匯入 CSV」或手動新增。
          </p>
          {lookup.data.results.map((r, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg bg-slate-100 px-3 py-2 text-sm dark:bg-slate-800">
              <span>{r.violation_date}・{r.violation}・{money(r.amount)}</span>
              <button className="btn-ghost btn-sm" onClick={() => {
                setForm({ violation_date: r.violation_date, violation: r.violation, location: r.location, amount: String(r.amount), fine_no: r.fine_no, due_date: r.due_date ?? "" });
                setAdding(true);
              }}>加入</button>
            </div>
          ))}
        </div>
      )}
      {adding && (
        <form className="card space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <div className="grid grid-cols-2 gap-3">
            <Field label="違規日期"><input className="input" type="date" value={form.violation_date} onChange={(e) => setForm({ ...form, violation_date: e.target.value })} required /></Field>
            <Field label="金額 $"><input className="input" inputMode="numeric" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} required /></Field>
            <Field label="違規事由" className="col-span-2"><input className="input" value={form.violation} onChange={(e) => setForm({ ...form, violation: e.target.value })} /></Field>
            <Field label="地點"><input className="input" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></Field>
            <Field label="繳費期限"><input className="input" type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} /></Field>
            <Field label="單號" className="col-span-2"><input className="input" value={form.fine_no} onChange={(e) => setForm({ ...form, fine_no: e.target.value })} /></Field>
          </div>
          <ErrorText error={create.error} />
          <button className="btn-primary w-full" disabled={create.isPending}>儲存</button>
        </form>
      )}
      <OfficialLinks topic="fines" />
      {list.data?.length === 0 && <Empty>沒有罰單記錄</Empty>}
      <ul className="space-y-2">
        {list.data?.map((f) => (
          <li key={f.id} className="card space-y-2">
            <button className="flex w-full items-start justify-between gap-3 text-left" onClick={() => setOpen(open === f.id ? null : f.id)}>
              <div>
                <div className="font-semibold">{f.violation || "罰單"}</div>
                <div className="text-xs text-slate-500">{f.violation_date}{f.location && `・${f.location}`}{f.due_date && `・期限 ${f.due_date}`}</div>
              </div>
              <div className="text-right">
                <div className="font-semibold tabular-nums">{money(f.amount)}</div>
                {f.paid_date ? <Chip tone="green">已繳</Chip> : f.overdue ? <Chip tone="red">逾期</Chip> : <Chip tone="amber">未繳</Chip>}
              </div>
            </button>
            {open === f.id && (
              <div className="space-y-3 border-t border-slate-200 pt-3 dark:border-slate-800">
                <div className="flex justify-end gap-2">
                  {!f.paid_date && <button className="btn-primary btn-sm" onClick={() => markPaid.mutate(f as never)}>標記已繳</button>}
                  <ConfirmButton onConfirm={() => remove.mutate(f.id)}>刪除</ConfirmButton>
                </div>
                <Attachments ownerType="fine" ownerId={f.id} title="罰單／繳費收據" />
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Expenses_({ vid }: { vid: number }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["expenses", vid], queryFn: () => api.expenses(vid) });
  const [date, setDate] = useState(today());
  const [cat, setCat] = useState<ExpenseCategory>("parking");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["expenses"] });
  const create = useMutation({
    mutationFn: () => api.createExpense(vid, { expense_date: date, category: cat, amount: toNum(amount) ?? 0, note: note.trim() }),
    onSuccess: () => { setAmount(""); setNote(""); refresh(); },
  });
  const remove = useMutation({ mutationFn: (id: number) => api.deleteExpense(id), onSuccess: refresh });
  return (
    <div className="space-y-3">
      <form className="card space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="日期"><input className="input" type="date" max={today()} value={date} onChange={(e) => setDate(e.target.value)} /></Field>
          <Field label="類別">
            <select className="input" value={cat} onChange={(e) => setCat(e.target.value as ExpenseCategory)}>
              {Object.entries(EXPENSE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </Field>
          <Field label="金額 $"><input className="input tabular-nums" inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} required /></Field>
          <Field label="備註"><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        </div>
        <ErrorText error={create.error ?? remove.error} />
        <button className="btn-primary w-full" disabled={create.isPending || !amount}>新增支出</button>
      </form>
      {list.data?.length === 0 && <Empty>沒有記錄</Empty>}
      <ul className="space-y-2">
        {list.data?.map((e) => (
          <li key={e.id} className="card flex items-center justify-between gap-3">
            <div>
              <div className="font-medium">{EXPENSE_LABEL[e.category]}</div>
              <div className="text-xs text-slate-500">{e.expense_date}{e.note && `・${e.note}`}</div>
            </div>
            <div className="flex items-center gap-3">
              <span className="font-semibold tabular-nums">{money(e.amount)}</span>
              <ConfirmButton onConfirm={() => remove.mutate(e.id)} className="btn-danger btn-sm !px-2">{""}</ConfirmButton>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Etag({ vid }: { vid: number }) {
  const qc = useQueryClient();
  const data = useQuery({ queryKey: ["etag", vid], queryFn: () => api.etag(vid) });
  const [kind, setKind] = useState<"topup" | "toll" | "balance_adjust">("topup");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["etag"] });
  const create = useMutation({
    mutationFn: () => api.createEtag(vid, { entry_date: today(), kind, amount: toNum(amount) ?? 0, note: note.trim() }),
    onSuccess: () => { setAmount(""); setNote(""); refresh(); },
  });
  const remove = useMutation({ mutationFn: (id: number) => api.deleteEtag(id), onSuccess: refresh });
  const KIND = { topup: "儲值", toll: "通行費", balance_adjust: "餘額校正" } as const;
  return (
    <div className="space-y-3">
      <div className="card text-center">
        <div className="label !mb-0">etag 餘額</div>
        <div className="font-serif text-3xl font-semibold tabular-nums">{money(data.data?.balance ?? 0)}</div>
        <p className="mt-1 text-[11px] text-slate-500">依你記錄的儲值與通行費推算；遠通未提供開放查詢，實際餘額請以官方為準，可用「校正」對齊。</p>
      </div>
      <OfficialLinks topic="etag" />
      <form className="card space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <Tabs value={kind} onChange={setKind} tabs={[
          { id: "topup", label: "儲值" }, { id: "toll", label: "通行費" }, { id: "balance_adjust", label: "校正" },
        ]} />
        <div className="grid grid-cols-2 gap-3">
          <Field label={kind === "balance_adjust" ? "差額 $（可為負）" : "金額 $"}>
            <input className="input tabular-nums" inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} required />
          </Field>
          <Field label="備註"><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        </div>
        <ErrorText error={create.error ?? remove.error} />
        <button className="btn-primary w-full" disabled={create.isPending || !amount}>新增</button>
      </form>
      <ul className="space-y-2">
        {data.data?.entries.map((e) => (
          <li key={e.id} className="card flex items-center justify-between">
            <div>
              <div className="font-medium">{KIND[e.kind]}</div>
              <div className="text-xs text-slate-500">{e.entry_date}{e.note && `・${e.note}`}</div>
            </div>
            <div className="flex items-center gap-3">
              <span className={`font-semibold tabular-nums ${e.kind === "toll" ? "text-red-500" : ""}`}>
                {e.kind === "toll" ? "−" : e.amount < 0 ? "−" : "+"}{money(Math.abs(e.amount))}
              </span>
              <ConfirmButton onConfirm={() => remove.mutate(e.id)} className="btn-danger btn-sm !px-2">{""}</ConfirmButton>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ───────────── 全國路邊停車費欠費查詢 ─────────────
const CAR_TYPE_OPTIONS = [
  { value: "M", label: "機車／重機" },
  { value: "C", label: "汽車" },
  { value: "O", label: "其他" },
];
const CITY_KEY = "motoq.parkingCity";

function BillRow({ b }: { b: ParkingBill }) {
  return (
    <li className="flex items-start justify-between gap-3 rounded-xl bg-slate-100 px-3 py-2.5 text-sm dark:bg-slate-800">
      <div className="min-w-0">
        <div className="font-medium">{b.parking_date || "停車單"}</div>
        <div className="text-xs text-slate-500">
          單號 {b.bill_no || "—"}
          {b.hours != null && `・${nf(b.hours, 1)} 小時`}
          {b.pay_limit_date && `・繳費期限 ${b.pay_limit_date}`}
        </div>
      </div>
      <div className="font-semibold tabular-nums">{money(b.pay_amount || b.amount)}</div>
    </li>
  );
}

function ResultCard({ r }: { r: ParkingResult }) {
  return (
    <div className="space-y-3">
      <div className={`card text-center ${r.total_count > 0 ? "!ring-amber-500/60" : ""}`}>
        <div className="label !mb-0">{r.plate}・{r.car_type_label}・{r.city}</div>
        {r.total_count > 0 ? (
          <>
            <div className="mt-1 font-serif text-3xl font-semibold tabular-nums">{money(r.total_amount)}</div>
            <div className="text-xs text-slate-500">共 {r.total_count} 筆待繳{r.update_time && `・資料更新 ${r.update_time}`}</div>
          </>
        ) : (
          <div className="mt-2 text-sm text-emerald-600 dark:text-emerald-400">目前沒有待繳的停車費 ✓</div>
        )}
        {r.cached && <div className="mt-1 text-[11px] text-slate-500">5 分鐘內的重複查詢，顯示快取結果</div>}
        {r.insecure && <div className="mt-1 text-[11px] text-amber-600">此縣市官方僅提供未加密連線</div>}
      </div>

      {r.reminders.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">催繳單</h3>
          {r.reminders.map((m, i) => (
            <div key={m.reminder_no || i} className="card space-y-2">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium">催繳單 {m.reminder_no || ""}</div>
                  <div className="text-xs text-slate-500">
                    {m.limit_date && `繳費期限 ${m.limit_date}`}
                    {m.extra_charge > 0 && `・含工本費 ${money(m.extra_charge)}`}
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-semibold tabular-nums">{money(m.pay_amount)}</div>
                  {m.prosecuted && <Chip tone="red">已移送</Chip>}
                </div>
              </div>
              {m.prosecute_limit_date && !m.prosecuted && (
                <p className="text-xs text-amber-600 dark:text-amber-400">逾 {m.prosecute_limit_date} 未繳，將移送強制執行</p>
              )}
              {m.bills.length > 0 && <ul className="space-y-1.5">{m.bills.map((b, j) => <BillRow key={b.bill_no || j} b={b} />)}</ul>}
            </div>
          ))}
        </div>
      )}
      {r.bills.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">停車繳費單</h3>
          <ul className="space-y-2">{r.bills.map((b, i) => <BillRow key={b.bill_no || i} b={b} />)}</ul>
        </div>
      )}
      {r.total_count > 0 && <a href={r.pay_url} target="_blank" rel="noreferrer" className="btn-ghost w-full">前往官方網站繳費</a>}
    </div>
  );
}

function ParkingLookup({ vehicleId, plate: vehiclePlate, vehicleType }: { vehicleId: number; plate: string; vehicleType: VehicleType }) {
  const qc = useQueryClient();
  const cities = useQuery({ queryKey: ["parkingCities"], queryFn: api.parkingCities, staleTime: Infinity });
  const checks = useQuery({ queryKey: ["parkingChecks", vehicleId], queryFn: () => api.parkingChecks(vehicleId) });
  const [plate, setPlate] = useState(vehiclePlate);
  const [carType, setCarType] = useState(vehicleType === "car" ? "C" : "M");
  const [city, setCity] = useState(() => {
    try { return localStorage.getItem(CITY_KEY) || "TPE"; } catch { return "TPE"; }
  });
  const [results, setResults] = useState<ParkingResult[]>([]);
  const [sweep, setSweep] = useState<{ done: number; total: number; failed: string[] } | null>(null);

  const single = useMutation<ParkingResult, Error>({
    mutationFn: () => api.parkingLookup(plate.trim(), carType, city, vehicleId),
    onSuccess: (r) => {
      setResults([r]);
      setSweep(null);
      qc.invalidateQueries({ queryKey: ["parkingChecks"] });
      qc.invalidateQueries({ queryKey: ["attention"] });
    },
  });
  const all = useMutation({
    mutationFn: async () => {
      const list = cities.data ?? [];
      const found: ParkingResult[] = [];
      const failed: string[] = [];
      setResults([]);
      for (let i = 0; i < list.length; i++) {
        setSweep({ done: i, total: list.length, failed });
        try {
          found.push(await api.parkingLookup(plate.trim(), carType, list[i].code, vehicleId));
        } catch (e) {
          if (e instanceof Error && /次數過多/.test(e.message)) throw e;
          failed.push(list[i].name);
        }
        setResults(found.filter((r) => r.total_count > 0));
      }
      setSweep({ done: list.length, total: list.length, failed });
      return found;
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["parkingChecks"] });
      qc.invalidateQueries({ queryKey: ["attention"] });
    },
  });
  const busy = single.isPending || all.isPending;

  const saved = (checks.data ?? []).filter((c) => c.total_count > 0);

  return (
    <div className="space-y-3">
      <form className="card space-y-3" onSubmit={(e) => { e.preventDefault(); single.mutate(); }}>
        <div>
          <h2 className="text-base font-semibold">路邊停車費欠費查詢</h2>
          <p className="text-xs text-slate-500">
            輸入車牌即可查詢各縣市尚未繳納的停車單與催繳單（含工本費、是否已移送）。資料來自各縣市政府公開的查詢服務，不需驗證碼。
          </p>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Field label="車牌號碼" className="col-span-2">
            <input className="input uppercase" value={plate} maxLength={12} placeholder="ABC-1234" autoCapitalize="characters"
              onChange={(e) => setPlate(e.target.value)} required />
          </Field>
          <Field label="車種">
            <select className="input" value={carType} onChange={(e) => setCarType(e.target.value)}>
              {CAR_TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </Field>
        </div>
        <Field label="縣市">
          <select className="input" value={city} onChange={(e) => { setCity(e.target.value); try { localStorage.setItem(CITY_KEY, e.target.value); } catch { /* 無痕模式 */ } }}>
            {(cities.data ?? [{ code: "TPE", name: "臺北市" }]).map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
          </select>
        </Field>
        <ErrorText error={single.error ?? all.error} />
        <div className="grid grid-cols-2 gap-2">
          <button className="btn-primary" disabled={busy || !plate.trim()}>
            <Icon name="parking" className="h-5 w-5" />
            {single.isPending ? "查詢中…" : "查詢此縣市"}
          </button>
          <button type="button" className="btn-ghost" disabled={busy || !plate.trim() || !cities.data}
            onClick={() => all.mutate()}>
            {all.isPending ? "查詢中…" : "查全台 21 縣市"}
          </button>
        </div>
        {sweep && (
          <div className="space-y-1">
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
              <div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${(sweep.done / sweep.total) * 100}%` }} />
            </div>
            <p className="text-xs text-slate-500">
              已查 {sweep.done}／{sweep.total} 個縣市（官方限制每秒 1 次，全台約需 1 分鐘）
              {sweep.done === sweep.total && (results.length === 0 ? "・全台皆無欠費 ✓" : `・${results.length} 個縣市有欠費`)}
              {sweep.failed.length > 0 && `・無法連線：${sweep.failed.join("、")}`}
            </p>
          </div>
        )}
      </form>

      {results.map((r) => <ResultCard key={r.city_code} r={r} />)}

      {results.length === 0 && saved.length > 0 && (
        <section className="card space-y-2">
          <h3 className="text-sm font-semibold">最近一次檢查發現的欠費</h3>
          {saved.map((c) => (
            <div key={c.city_code} className="flex items-center justify-between text-sm">
              <span>{c.city}・{c.total_count} 筆</span>
              <span className="font-semibold tabular-nums">{money(c.total_amount)}</span>
            </div>
          ))}
          <p className="text-[11px] text-slate-500">
            {new Date(saved[0].checked_at + "Z").toLocaleString("zh-TW", { hour12: false })} 檢查
            {saved[0].source === "auto" ? "（自動）" : ""}。可在「設定」開啟每日自動檢查。
          </p>
        </section>
      )}

      <p className="text-center text-[11px] leading-relaxed text-slate-500">
        僅供參考，實際金額與狀態以各縣市政府為準。官方系統每日約 05:15–06:15 更新資料，期間可能無法查詢。
      </p>
    </div>
  );
}
