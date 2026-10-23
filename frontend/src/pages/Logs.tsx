import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Chip, Empty, PageTitle } from "../components/ui";
import { SOURCE_LABEL, money, nf } from "../lib";
import { useVehicle } from "../vehicleContext";

export default function Logs() {
  const { vehicle } = useVehicle();
  const vid = vehicle?.id;
  const logs = useQuery({ queryKey: ["logs", vid], queryFn: () => api.logs(vid!), enabled: !!vid });
  if (!vehicle) return <Empty>請先新增車輛</Empty>;
  const electricOnly = vehicle.energy_type === "electric";

  return (
    <div className="space-y-3">
      <PageTitle>{electricOnly ? "充電記錄" : vehicle.energy_type === "hybrid" ? "加油／充電記錄" : "加油記錄"}</PageTitle>
      {logs.isLoading && <p className="text-center text-slate-500">載入中…</p>}
      {logs.data?.length === 0 && <Empty>還沒有記錄</Empty>}
      <ul className="space-y-2">
        {logs.data?.map((l) => (
          <li key={l.id}>
            <Link to={`/logs/${l.id}/edit`} className="card block">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-semibold">{l.log_date}</div>
                  <div className="text-xs text-slate-500">
                    {nf(l.odometer_km)} km{l.distance_km != null && `（+${nf(l.distance_km)}）`}
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-semibold tabular-nums">{money(l.total_amount)}</div>
                  <div className="text-xs text-slate-500">
                    {nf(l.quantity, 2)} {l.unit} × {nf(l.unit_price, 1)}
                  </div>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <Chip>{SOURCE_LABEL[l.energy_source]}</Chip>
                {!l.is_full && <Chip tone="amber">未加滿</Chip>}
                {l.missed_before && <Chip tone="red">前次漏記</Chip>}
                {l.efficiency != null && (
                  <Chip tone="gold">{nf(l.efficiency, 1)} km/{l.unit}・{nf(l.cost_per_km, 2)} 元/km</Chip>
                )}
                {l.station && <span className="text-xs text-slate-500">{l.station}</span>}
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
