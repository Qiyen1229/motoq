import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type MaintItemInput, type MaintStatusItem } from "../api";
import { Chip, ConfirmButton, Empty, ErrorText, Field, PageTitle, Progress } from "../components/ui";
import { nf, today, toNum } from "../lib";
import { useVehicle } from "../vehicleContext";

const STATE_LABEL = { overdue: "已逾期", soon: "即將到期", ok: "正常", unknown: "尚無基準" } as const;
const STATE_TONE = { overdue: "red", soon: "amber", ok: "green", unknown: "gray" } as const;

function describe(m: MaintStatusItem): string {
  const parts: string[] = [];
  if (m.interval_km) parts.push(`每 ${nf(m.interval_km)} km`);
  if (m.interval_months) parts.push(`每 ${m.interval_months} 個月`);
  return parts.join(" 或 ") + "（先到先提醒）";
}

export default function Maintenance() {
  const { vehicle } = useVehicle();
  const vid = vehicle?.id;
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["maint", vid], queryFn: () => api.maintStatus(vid!), enabled: !!vid });
  const [adding, setAdding] = useState(false);
  const [baselineDate, setBaselineDate] = useState("");
  const [baselineKm, setBaselineKm] = useState("");

  const refresh = () => { qc.invalidateQueries({ queryKey: ["maint", vid] }); qc.invalidateQueries({ queryKey: ["attention"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }); };
  const applyTpl = useMutation({
    mutationFn: () => api.applyTemplate(vid!, { baseline_date: baselineDate || null, baseline_km: toNum(baselineKm) }),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: (id: number) => api.deleteItem(id), onSuccess: refresh });

  if (!vehicle) return <Empty>請先新增車輛</Empty>;
  const data = status.data;
  const items = data?.items ?? [];

  return (
    <div className="space-y-4">
      <PageTitle action={
        <div className="flex gap-2">
          <Link to="/service" className="btn-ghost btn-sm">履歷</Link>
          <Link to="/service/new" className="btn-primary btn-sm">＋ 記錄保養</Link>
        </div>
      }>保養與耗材</PageTitle>

      {data && (
        <p className="text-xs text-slate-500">
          目前 {nf(data.current_km)} km・
          {data.daily_km ? `平均每日約 ${nf(data.daily_km, 1)} km（用於預測到期日）` : "資料不足，暫無法依里程預測日期"}
        </p>
      )}

      {items.length === 0 && !status.isLoading && (
        <section className="card space-y-3">
          <h2 className="text-base font-semibold">建立保養項目</h2>
          <p className="text-sm text-slate-500">
            依「{vehicle.vehicle_type === "car" ? "汽車" : vehicle.vehicle_type === "scooter" ? "機車" : "重機"}・
            {vehicle.energy_type === "electric" ? "純電" : vehicle.energy_type === "hybrid" ? "油電" : "燃油"}」套用常見項目，之後都可自行調整間隔。
          </p>
          <div className="grid grid-cols-2 gap-3 items-start">
            <Field label="上次保養日期" hint="選填">

              <input className="input" type="date" max={today()} value={baselineDate} onChange={(e) => setBaselineDate(e.target.value)} />
            </Field>
            <Field label="當時里程" hint="選填 (km)">
              <input className="input tabular-nums" inputMode="numeric" value={baselineKm} onChange={(e) => setBaselineKm(e.target.value)} />
            </Field>
          </div>

          <p className="text-xs text-slate-500">不填也可以，之後第一次記錄保養時才開始計算。</p>
          <ErrorText error={applyTpl.error} />
          <button className="btn-primary w-full" disabled={applyTpl.isPending} onClick={() => applyTpl.mutate()}>套用範本</button>
        </section>
      )}

      <ul className="space-y-2">
        {items.map((m) => (
          <li key={m.item_id} className="card space-y-2">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold">{m.name}</div>
                <div className="text-xs text-slate-500">{m.category}・{describe(m)}</div>
              </div>
              <Chip tone={STATE_TONE[m.state]}>{STATE_LABEL[m.state]}</Chip>
            </div>
            {m.progress != null && <Progress value={m.progress} tone={m.state === "overdue" ? "overdue" : m.state === "soon" ? "soon" : "ok"} />}
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
              <span>
                {m.last_date ? `上次 ${m.last_date}・${nf(m.last_km)} km` : "尚無更換記錄"}
              </span>
              <span className="tabular-nums">
                {m.remaining_km != null && (m.remaining_km < 0 ? `超過 ${nf(-m.remaining_km)} km` : `剩 ${nf(m.remaining_km)} km`)}
                {m.remaining_km != null && m.due_date && "・"}
                {m.due_date && `${m.basis === "time" ? "時間" : "里程"}先到 ${m.due_date}`}
              </span>
            </div>
            <div className="flex justify-end gap-2">
              <Link to={`/service/new?item=${m.item_id}`} className="btn-ghost btn-sm">已更換</Link>
              <ConfirmButton onConfirm={() => remove.mutate(m.item_id)}>移除</ConfirmButton>
            </div>
          </li>
        ))}
      </ul>

      {items.length > 0 && (
        <button className="btn-ghost w-full" onClick={() => setAdding(!adding)}>
          {adding ? "取消" : "＋ 自訂項目"}
        </button>
      )}
      {adding && vid && <CustomItemForm vehicleId={vid} onDone={() => { setAdding(false); refresh(); }} />}
      <ErrorText error={remove.error} />
    </div>
  );
}

function CustomItemForm({ vehicleId, onDone }: { vehicleId: number; onDone: () => void }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("其他");
  const [km, setKm] = useState("");
  const [months, setMonths] = useState("");
  const [bDate, setBDate] = useState("");
  const [bKm, setBKm] = useState("");
  const create = useMutation({
    mutationFn: () => {
      const body: MaintItemInput = {
        name: name.trim(), category, interval_km: toNum(km), interval_months: toNum(months),
        baseline_date: bDate || null, baseline_km: toNum(bKm), is_active: true, note: "",
      };
      return api.createItem(vehicleId, body);
    },
    onSuccess: onDone,
  });
  return (
    <form className="card space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="名稱"><input className="input" value={name} onChange={(e) => setName(e.target.value)} required placeholder="例：鏈條上油" /></Field>
        <Field label="分類">
          <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
            {["引擎", "傳動", "煞車", "輪胎", "電系", "車身", "其他"].map((c) => <option key={c}>{c}</option>)}
          </select>
        </Field>
        <Field label="每幾 km"><input className="input" inputMode="numeric" value={km} onChange={(e) => setKm(e.target.value)} /></Field>
        <Field label="每幾個月"><input className="input" inputMode="numeric" value={months} onChange={(e) => setMonths(e.target.value)} /></Field>
        <Field label="上次日期（選填）"><input className="input" type="date" max={today()} value={bDate} onChange={(e) => setBDate(e.target.value)} /></Field>
        <Field label="當時里程（選填）"><input className="input" inputMode="numeric" value={bKm} onChange={(e) => setBKm(e.target.value)} /></Field>
      </div>
      <p className="text-xs text-slate-500">里程與時間至少填一項；兩項都填時，先到者先提醒。</p>
      <ErrorText error={create.error} />
      <button className="btn-primary w-full" disabled={create.isPending || !name.trim() || (!km && !months)}>新增項目</button>
    </form>
  );
}
