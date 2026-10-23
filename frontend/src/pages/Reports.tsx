import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type PeriodReport } from "../api";
import { Empty, ErrorText, Field, PageTitle, Stat, Tabs } from "../components/ui";
import { money, nf, vehicleName, VEHICLE_TYPE_LABEL } from "../lib";
import { useVehicle } from "../vehicleContext";

const GOLD_SHADES = ["#c9a24a", "#e2c46c", "#9c7b2b", "#d6d0c4", "#8d8a82", "#5f5c55", "#3b3935"];
const tooltipStyle = { background: "#171716", border: "1px solid #3b3935", borderRadius: 10, color: "#f7f6f3" };

export default function Reports() {
  const [tab, setTab] = useState<"annual" | "compare">("annual");
  const { vehicles } = useVehicle();
  return (
    <div className="space-y-4">
      <PageTitle>報表</PageTitle>
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "annual", label: "年度持有成本" }, { id: "compare", label: "兩車比較" }]} />
      {tab === "annual" ? <Annual /> : vehicles.length >= 2 ? <Compare /> : <Empty>需要至少兩台車才能比較。</Empty>}
    </div>
  );
}

function Breakdown({ r }: { r: PeriodReport }) {
  const nonZero = r.categories.filter((c) => c.amount > 0);
  return (
    <ul className="space-y-2.5">
      {nonZero.length === 0 && <li className="text-sm text-slate-500">此期間沒有費用記錄</li>}
      {nonZero.map((c, i) => (
        <li key={c.key}>
          <div className="mb-1 flex justify-between text-sm">
            <span>{c.label}</span>
            <span className="tabular-nums">{money(c.amount)}・{r.total_cost ? Math.round((c.amount / r.total_cost) * 100) : 0}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
            <div className="h-full rounded-full" style={{ width: `${(c.amount / r.total_cost) * 100}%`, background: GOLD_SHADES[i % GOLD_SHADES.length] }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function Annual() {
  const { vehicle } = useVehicle();
  const vid = vehicle?.id;
  const qc = useQueryClient();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const rep = useQuery({ queryKey: ["annual", vid, year], queryFn: () => api.annual(vid!, year), enabled: !!vid });
  const saved = useQuery({ queryKey: ["annualSaved", vid], queryFn: () => api.savedAnnual(vid!), enabled: !!vid });
  const save = useMutation({ mutationFn: () => api.saveAnnual(vid!, year), onSuccess: () => qc.invalidateQueries({ queryKey: ["annualSaved"] }) });
  if (!vehicle) return <Empty>請先新增車輛</Empty>;
  const r = rep.data;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <select className="input !w-auto" value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="年度">
          {Array.from({ length: 6 }, (_, i) => thisYear - i).map((y) => <option key={y} value={y}>{y} 年</option>)}
        </select>
        <button className="btn-ghost btn-sm" onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isSuccess ? "已存檔 ✓" : "存成年度報告"}
        </button>
      </div>
      <ErrorText error={save.error} />
      {r && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <Stat label="年度總成本" value={money(r.total_cost)} />
            <Stat label="每公里持有成本" value={r.cost_per_km != null ? `$${nf(r.cost_per_km, 2)}` : "—"} sub={`行駛 ${nf(r.distance_km)} km`} />
          </div>
          <section className="card space-y-3">
            <h2 className="text-base font-semibold">費用結構</h2>
            <Breakdown r={r} />
          </section>
          {r.monthly.length > 0 && (
            <section className="card">
              <h2 className="mb-2 text-base font-semibold">逐月支出</h2>
              <div className="h-48 text-slate-500">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={r.monthly.map((m) => ({ ...m, label: m.month.slice(5) + "月" }))} margin={{ left: -12, right: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.18} vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 11, fill: "currentColor" }} stroke="currentColor" strokeOpacity={0.3} />
                    <YAxis tick={{ fontSize: 11, fill: "currentColor" }} stroke="currentColor" strokeOpacity={0.3} />
                    <Tooltip contentStyle={tooltipStyle} formatter={(v) => [money(Number(v)), "支出"]} cursor={{ fill: "rgba(201,162,74,0.1)" }} />
                    <Bar dataKey="amount" fill="#c9a24a" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          )}
          {r.avg_efficiency != null && (
            <p className="text-center text-xs text-slate-500">
              當年平均 {nf(r.avg_efficiency, 1)} {r.efficiency_unit}
              {r.energy_cost_per_km != null && `・能源費 $${nf(r.energy_cost_per_km, 2)}/km`}
            </p>
          )}
        </>
      )}
      {saved.data && saved.data.length > 0 && (
        <p className="text-xs text-slate-500">
          已保存的年度報告：{saved.data.map((s) => `${s.year}（${s.trigger === "auto" ? "自動" : "手動"}）`).join("、")}。每年 12/31 會自動產生。
        </p>
      )}
    </div>
  );
}

function Compare() {
  const { vehicles } = useVehicle();
  const y = new Date().getFullYear();
  const [ids, setIds] = useState<number[]>(vehicles.slice(0, 2).map((v) => v.id));
  const [from, setFrom] = useState(`${y}-01-01`);
  const [to, setTo] = useState(`${y}-12-31`);
  const q = useQuery({ queryKey: ["compare", ids, from, to], queryFn: () => api.compare(ids, from, to), enabled: ids.length >= 2 });
  const data = q.data ?? [];
  const cats = useMemo(() => (data[0]?.categories ?? []).map((c) => c.key), [data]);

  const toggle = (id: number) => setIds((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id].slice(-6)));

  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <div className="flex flex-wrap gap-2">
          {vehicles.map((v) => (
            <button key={v.id} onClick={() => toggle(v.id)}
              className={`rounded-full border px-3 py-1.5 text-sm ${ids.includes(v.id) ? "border-brand-500 bg-brand-500/15 text-brand-800 dark:text-brand-300" : "border-slate-300 text-slate-500 dark:border-slate-700"}`}>
              {VEHICLE_TYPE_LABEL[v.vehicle_type]}・{vehicleName(v)}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="起"><input className="input" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
          <Field label="迄"><input className="input" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        </div>
      </div>
      <ErrorText error={q.error} />
      {ids.length < 2 && <Empty>請至少選擇兩台車</Empty>}
      {data.length >= 2 && (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[420px] text-sm">
            <thead>
              <tr className="hairline text-left text-xs uppercase tracking-wider text-slate-500">
                <th className="py-2 pr-2 font-medium">項目</th>
                {data.map((d) => <th key={d.vehicle_id} className="px-2 py-2 text-right font-medium">{d.vehicle}</th>)}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              <tr className="hairline"><td className="py-2 pr-2">行駛里程</td>{data.map((d) => <td key={d.vehicle_id} className="px-2 text-right">{nf(d.distance_km)} km</td>)}</tr>
              <tr className="hairline font-semibold"><td className="py-2 pr-2">總成本</td>{data.map((d) => <td key={d.vehicle_id} className="px-2 text-right">{money(d.total_cost)}</td>)}</tr>
              <tr className="hairline font-semibold"><td className="py-2 pr-2 gold-text">每公里成本</td>{data.map((d) => <td key={d.vehicle_id} className="px-2 text-right gold-text">{d.cost_per_km != null ? `$${nf(d.cost_per_km, 2)}` : "—"}</td>)}</tr>
              {cats.map((k) => (
                <tr key={k} className="hairline text-slate-600 dark:text-slate-300">
                  <td className="py-2 pr-2">{data[0].categories.find((c) => c.key === k)?.label}</td>
                  {data.map((d) => <td key={d.vehicle_id} className="px-2 text-right">{money(d.categories.find((c) => c.key === k)?.amount ?? 0)}</td>)}
                </tr>
              ))}
              <tr><td className="py-2 pr-2">平均能耗</td>{data.map((d) => <td key={d.vehicle_id} className="px-2 text-right">{d.avg_efficiency != null ? `${nf(d.avg_efficiency, 1)} ${d.efficiency_unit}` : "—"}</td>)}</tr>
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-slate-500">稅金與保險以「實際繳費日」認列；罰單以違規日認列；里程為期間內首末里程記錄之差。</p>
    </div>
  );
}
