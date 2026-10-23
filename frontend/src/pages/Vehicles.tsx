import { Link } from "react-router-dom";
import { Chip, Empty, PageTitle } from "../components/ui";
import { ENERGY_TYPE_LABEL, VEHICLE_TYPE_LABEL, nf, vehicleName } from "../lib";
import { useVehicle } from "../vehicleContext";

export default function Vehicles() {
  const { vehicles, vehicle, setVehicleId } = useVehicle();
  return (
    <div className="space-y-3">
      <PageTitle action={<Link to="/vehicles/new" className="btn-primary btn-sm">＋ 新增</Link>}>我的車輛</PageTitle>
      {vehicles.length === 0 && <Empty>還沒有車輛</Empty>}
      <ul className="space-y-2">
        {vehicles.map((v) => (
          <li key={v.id} className={`card flex items-center justify-between ${vehicle?.id === v.id ? "!ring-2 !ring-brand-500" : ""}`}>
            <button className="flex-1 text-left" onClick={() => setVehicleId(v.id)}>
              <div className="font-semibold">{vehicleName(v)}</div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                <Chip tone="gold">{VEHICLE_TYPE_LABEL[v.vehicle_type]}・{ENERGY_TYPE_LABEL[v.energy_type]}</Chip>
                {v.displacement_cc ? `${v.displacement_cc}cc` : ""}
                {v.plate && <span>{v.plate}</span>}
                <span>{nf(v.current_odometer_km)} km</span>
                {vehicle?.id === v.id && <span className="gold-text">使用中</span>}
              </div>
            </button>
            <Link to={`/vehicles/${v.id}`} className="btn-ghost btn-sm ml-3">編輯</Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
