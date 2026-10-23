import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import Icon from "../components/Icon";
import { Empty, PageTitle } from "../components/ui";
import { money, nf } from "../lib";
import { useVehicle } from "../vehicleContext";

export default function Service() {
  const { vehicle } = useVehicle();
  const vid = vehicle?.id;
  const visits = useQuery({ queryKey: ["visits", vid], queryFn: () => api.visits(vid!), enabled: !!vid });
  if (!vehicle) return <Empty>請先新增車輛</Empty>;
  const total = (visits.data ?? []).reduce((s, v) => s + v.total_cost, 0);

  return (
    <div className="space-y-4">
      <PageTitle action={<Link to="/service/new" className="btn-primary btn-sm">＋ 新增</Link>}>維修履歷</PageTitle>

      <div className="card flex items-center justify-between">
        <div>
          <div className="label !mb-0">累計維修保養</div>
          <div className="font-serif text-2xl font-semibold tabular-nums">{money(total)}</div>
          <div className="text-xs text-slate-500">{visits.data?.length ?? 0} 次進廠／保養</div>
        </div>
        <div className="flex flex-col gap-2">
          <a className="btn-ghost btn-sm" href={`/api/v1/vehicles/${vid}/reports/service-history.pdf`} download>
            <Icon name="doc" className="h-4 w-4" />匯出 PDF
          </a>
          <a className="text-center text-xs underline gold-text" href={`/api/v1/vehicles/${vid}/reports/service-history.html`} target="_blank" rel="noreferrer">
            網頁版（可列印）
          </a>
        </div>
      </div>

      {visits.data?.length === 0 && <Empty>還沒有維修紀錄。賣車時，這份履歷可以一鍵匯出成 PDF。</Empty>}
      <ul className="space-y-2">
        {visits.data?.map((v) => (
          <li key={v.id}>
            <Link to={`/service/${v.id}`} className="card block space-y-1.5">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-semibold">{v.visit_date}</div>
                  <div className="text-xs text-slate-500">{nf(v.odometer_km)} km・{v.shop || "自行保養"}</div>
                </div>
                <div className="font-semibold tabular-nums">{money(v.total_cost)}</div>
              </div>
              {v.lines.length > 0 && (
                <div className="text-sm text-slate-600 dark:text-slate-300">
                  {v.lines.map((l) => l.item_name || l.description || l.part_name).filter(Boolean).join("、")}
                </div>
              )}
              {v.attachment_count > 0 && (
                <div className="flex items-center gap-1 text-xs text-slate-500">
                  <Icon name="camera" className="h-3.5 w-3.5" />{v.attachment_count} 張單據
                </div>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
