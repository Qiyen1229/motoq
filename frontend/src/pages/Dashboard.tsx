import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, type AttentionItem } from "../api";
import Icon from "../components/Icon";
import { Chip, Empty, Stat } from "../components/ui";
import { PRODUCT_LABEL, SOURCE_LABEL, money, nf, shortDate } from "../lib";
import { useVehicle } from "../vehicleContext";

const SEV_STYLE: Record<AttentionItem["severity"], string> = {
  critical: "border-red-500/60 bg-red-500/10",
  warning: "border-amber-500/50 bg-amber-500/10",
  info: "border-slate-300 bg-slate-100 dark:border-slate-700 dark:bg-slate-900",
};

export default function Dashboard() {
  const { vehicle, loading } = useVehicle();
  const location = useLocation();
  const [flash] = useState(() => (location.state as { flash?: string } | null)?.flash);
  useEffect(() => {
    // 提示只顯示一次：清掉 history state，重新整理或返回時不會再出現
    if (flash) window.history.replaceState({}, "");
  }, [flash]);
  const [metric, setMetric] = useState<"efficiency" | "cost_per_km">("efficiency");
  const vid = vehicle?.id;

  const dash = useQuery({ queryKey: ["dashboard", vid], queryFn: () => api.dashboard(vid!), enabled: !!vid });
  const trend = useQuery({ queryKey: ["trend", vid], queryFn: () => api.trend(vid!), enabled: !!vid });
  const recent = useQuery({ queryKey: ["logs", vid, 5], queryFn: () => api.logs(vid!, 5), enabled: !!vid });
  const attention = useQuery({ queryKey: ["attention"], queryFn: api.attention });
  const fuel = useQuery({ queryKey: ["fuel"], queryFn: api.fuelLatest });

  if (loading) return <p className="text-center text-slate-500">載入中…</p>;
  if (!vehicle)
    return (
      <Empty>
        <p className="mb-4">還沒有車輛，先新增一台吧</p>
        <Link to="/vehicles/new" className="btn-primary">新增車輛</Link>
      </Empty>
    );

  const d = dash.data;
  const electric = vehicle.energy_type === "electric";
  const points = (trend.data ?? []).map((t) => ({
    date: shortDate(t.end_date),
    value: metric === "efficiency" ? t.efficiency : t.cost_per_km,
  }));
  const todo = (attention.data ?? []).filter((a) => a.severity !== "info" || a.vehicle_id === vehicle.id);
  const nm = d?.next_maintenance;

  return (
    <div className="space-y-5">
      {flash && (
        <div role="status" className="rounded-xl border border-brand-500/40 bg-brand-500/10 px-4 py-3 text-sm font-medium text-brand-800 dark:text-brand-300">
          {flash}
        </div>
      )}

      {todo.length > 0 && (
        <section aria-label="待辦事項" className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">待辦事項</h2>
          {todo.slice(0, 5).map((a, i) => (
            <Link key={i} to={a.link} className={`flex items-start gap-3 rounded-xl border px-3 py-2.5 ${SEV_STYLE[a.severity]}`}>
              <Icon name="warn" className={`mt-0.5 h-5 w-5 shrink-0 ${a.severity === "critical" ? "text-red-500" : "text-amber-500"}`} />
              <div className="min-w-0">
                <div className="text-sm font-semibold">{a.title}</div>
                <div className="truncate text-xs text-slate-500">{a.vehicle}・{a.detail}</div>
              </div>
            </Link>
          ))}
          {todo.length > 5 && <p className="text-center text-xs text-slate-500">還有 {todo.length - 5} 項</p>}
        </section>
      )}

      <div className="grid grid-cols-2 gap-3 items-stretch">
        <Stat label="總里程" value={<>{nf(d?.total_km)}<span className="ml-1 font-sans text-sm font-normal text-slate-500">km</span></>} sub="累積行駛" />
        <Stat label={`本月${electric ? "電費" : "能源費"}`} value={money(d?.month_cost)}
          sub={d ? `${nf(d.month_energy, 1)} ${d.energy_unit}・${d.month_log_count} 次` : "本月尚無記錄"} />
        <Stat label="平均油耗"
          value={d?.avg_efficiency != null
            ? <>{nf(d.avg_efficiency, 1)}<span className="ml-1 font-sans text-sm font-normal text-slate-500">{d.efficiency_unit}</span></> : "—"}
          sub={d?.last_efficiency != null ? `最近一次 ${nf(d.last_efficiency, 1)}` : "需至少兩次加滿"} />
        <Stat label="每公里費用" value={d?.cost_per_km != null ? `$${nf(d.cost_per_km, 2)}` : "—"} sub="能源費 ÷ 里程" />
      </div>

      <Link to="/maintenance" className="card flex items-center justify-between">
        <div>
          <div className="label !mb-0">下次保養</div>
          {nm ? (
            <>
              <div className="mt-1 text-lg font-semibold">{nm.name}</div>
              <div className="text-xs text-slate-500">
                {nm.remaining_km != null && (nm.remaining_km < 0 ? `里程已超過 ${nf(-nm.remaining_km)} km` : `剩 ${nf(nm.remaining_km)} km`)}
                {nm.remaining_km != null && nm.due_date && "・"}
                {nm.due_date && `預計 ${nm.due_date}`}
              </div>
            </>
          ) : (
            <div className="mt-1 text-sm text-slate-500">尚未設定保養項目，點此建立</div>
          )}
        </div>
        {nm && <Chip tone={nm.state === "overdue" ? "red" : nm.state === "soon" ? "amber" : "green"}>
          {nm.state === "overdue" ? "已逾期" : nm.state === "soon" ? "即將到期" : "正常"}
        </Chip>}
      </Link>

      <section className="card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">趨勢</h2>
          <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-sm dark:bg-slate-800">
            {([["efficiency", d?.efficiency_unit ?? "km/L"], ["cost_per_km", "元/km"]] as const).map(([k, label]) => (
              <button key={k} onClick={() => setMetric(k)}
                className={`rounded-md px-3 py-1 ${metric === k ? "bg-white font-semibold shadow dark:bg-slate-700 dark:text-brand-400" : "text-slate-500"}`}>
                {label}
              </button>
            ))}
          </div>
        </div>
        {points.length < 2 ? (
          <p className="py-10 text-center text-sm text-slate-500">
            累積至少兩個「加滿」區間後會顯示折線圖（目前 {points.length} 個）
          </p>
        ) : (
          <div className="h-56 text-slate-500">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.18} />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: "currentColor" }} stroke="currentColor" strokeOpacity={0.3} />
                <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11, fill: "currentColor" }} stroke="currentColor" strokeOpacity={0.3} />
                <Tooltip
                  contentStyle={{ background: "#171716", border: "1px solid #3b3935", borderRadius: 10, color: "#f7f6f3" }}
                  formatter={(v) => [nf(Number(v), 2), metric === "efficiency" ? d?.efficiency_unit : "元/km"]} />
                {metric === "efficiency" && d?.avg_efficiency != null && (
                  <ReferenceLine y={d.avg_efficiency} stroke="#9c988d" strokeDasharray="4 4" />
                )}
                <Line type="monotone" dataKey="value" stroke="#c9a24a" strokeWidth={2.5}
                  dot={{ r: 3, fill: "#c9a24a", strokeWidth: 0 }} activeDot={{ r: 5 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <section className="card">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-base font-semibold">中油牌價</h2>
          {fuel.data && fuel.data.length > 0 && (
            <span className="text-xs text-slate-500">{fuel.data[0].price_date} 生效</span>
          )}
        </div>
        {fuel.data && fuel.data.length > 0 ? (
          <>
            <ul className="grid grid-cols-4 gap-2 text-center">
              {fuel.data.map((p) => (
                <li key={p.product} className="flex flex-col justify-between h-full rounded-xl bg-slate-100 p-2 dark:bg-slate-800">
                  <div className="text-xs text-slate-500 font-medium">{PRODUCT_LABEL[p.product]}</div>
                  <div className="my-0.5 font-serif text-lg font-semibold tabular-nums leading-tight">{nf(p.price, 1)}</div>
                  <div className="flex h-4 items-center justify-center text-[11px] leading-none">
                    {p.change != null && p.change !== 0 ? (
                      <span className={p.change > 0 ? "text-red-500" : "text-emerald-500"}>
                        {p.change > 0 ? "▲" : "▼"} {nf(Math.abs(p.change), 1)}
                      </span>
                    ) : (
                      <span className="text-slate-400 dark:text-slate-600 font-mono">—</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11px] text-slate-500">加油時會依油品自動帶入單價；台塑、全國等站以此為參考。</p>
          </>
        ) : (

          <p className="py-3 text-center text-sm text-slate-500">
            {fuel.isLoading ? "取得中…" : "暫時無法取得中油牌價，稍後會自動重試（管理員也可在後台手動輸入）。"}
          </p>
        )}
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-base font-semibold">最近記錄</h2>
          <Link to="/logs" className="text-sm gold-text">全部</Link>
        </div>
        {recent.data?.length ? (
          <ul className="space-y-2">
            {recent.data.map((l) => (
              <li key={l.id}>
                <Link to={`/logs/${l.id}/edit`} className="card flex items-center justify-between">
                  <div>
                    <div className="font-medium">{l.log_date}</div>
                    <div className="text-xs text-slate-500">
                      {nf(l.odometer_km)} km・{SOURCE_LABEL[l.energy_source]}・{nf(l.quantity, 2)} {l.unit}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold tabular-nums">{money(l.total_amount)}</div>
                    {l.efficiency != null && <div className="text-xs gold-text">{nf(l.efficiency, 1)} km/{l.unit}</div>}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>還沒有記錄，點右下角按鈕新增第一筆</Empty>
        )}
      </section>
    </div>
  );
}
