import type { ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { VEHICLE_TYPE_LABEL, vehicleName } from "../lib";
import { useVehicle } from "../vehicleContext";
import Icon from "./Icon";

const tabs = [
  { to: "/", label: "首頁", icon: "home", end: true },
  { to: "/logs", label: "能源", icon: "fuel", end: false },
  { to: "/maintenance", label: "保養", icon: "wrench", end: false },
  { to: "/expenses", label: "費用", icon: "receipt", end: false },
  { to: "/more", label: "更多", icon: "grid", end: false },
];

const ROOTS = ["/", "/logs", "/maintenance", "/expenses", "/more"];

/** 沒有瀏覽歷史（直接開啟深層網址）時，返回的落點 */
function parentOf(path: string): string {
  if (path === "/add") return "/";
  if (path.startsWith("/logs/")) return "/logs";
  if (path.startsWith("/service/")) return "/service";
  if (path.startsWith("/vehicles/")) return "/vehicles";
  return "/more";
}

export default function Layout({ children }: { children: ReactNode }) {
  const { vehicles, vehicle, setVehicleId } = useVehicle();
  const { pathname, key } = useLocation();
  const navigate = useNavigate();
  const showBack = !ROOTS.includes(pathname);
  const goBack = () => (key !== "default" ? navigate(-1) : navigate(parentOf(pathname), { replace: true }));
  const showFab = pathname === "/" || pathname === "/logs";
  const electric = vehicle?.energy_type === "electric";

  return (
    <div className="mx-auto flex min-h-screen max-w-xl flex-col">
      <header className="sticky top-0 z-20 flex items-center gap-2 border-b border-slate-200 bg-white/95 px-3 pb-2.5 pt-[max(0.625rem,env(safe-area-inset-top))] text-slate-900 backdrop-blur dark:border-brand-500/30 dark:bg-slate-950/95 dark:text-slate-100">
        {showBack && (
          <button
            type="button"
            onClick={goBack}
            aria-label="返回上一頁"
            className="-ml-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-slate-700 hover:bg-slate-100 active:scale-95 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <Icon name="back" className="h-6 w-6" />
          </button>
        )}
        <Link to="/" className={`font-serif font-semibold tracking-[0.2em] text-brand-700 dark:text-brand-400 ${showBack ? "text-base" : "pl-1 text-xl"}`}>
          MOTOQ
        </Link>
        {vehicles.length > 0 && (
          <select
            aria-label="切換車輛"
            value={vehicle?.id ?? ""}
            onChange={(e) => setVehicleId(Number(e.target.value))}
            className="ml-auto max-w-[58%] truncate rounded-lg border border-slate-300 bg-slate-100 px-2 py-1.5 text-sm text-slate-900 outline-none focus:border-brand-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            {vehicles.map((v) => (
              <option key={v.id} value={v.id}>
                {VEHICLE_TYPE_LABEL[v.vehicle_type]}・{vehicleName(v)}
              </option>
            ))}
          </select>
        )}
      </header>

      <main className="flex-1 px-4 pb-36 pt-5">{children}</main>

      {vehicle && showFab && (
        <Link
          to="/add"
          aria-label="新增能源記錄"
          className="fixed bottom-24 right-[max(1rem,calc(50%-18rem))] z-30 flex h-14 items-center gap-2 rounded-full bg-brand-500 px-5 text-base font-bold text-slate-950 shadow-lg shadow-black/30 active:scale-95"
        >
          <Icon name={electric ? "bolt" : "fuel"} />
          {electric ? "充電" : "加油"}
        </Link>
      )}

      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur dark:border-slate-800 dark:bg-slate-950/95">
        <ul className="mx-auto grid max-w-xl grid-cols-5">
          {tabs.map((t) => (
            <li key={t.to}>
              <NavLink
                to={t.to}
                end={t.end}
                className={({ isActive }) =>
                  `flex flex-col items-center gap-0.5 py-2 text-[11px] tracking-wide ${
                    isActive ? "font-semibold text-brand-700 dark:text-brand-400" : "text-slate-500"
                  }`
                }
              >
                <Icon name={t.icon} className="h-[22px] w-[22px]" />
                {t.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
