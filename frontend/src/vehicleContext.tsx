import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type Vehicle } from "./api";

interface Ctx {
  vehicles: Vehicle[];
  vehicle: Vehicle | null;
  setVehicleId: (id: number) => void;
  loading: boolean;
}
const VehicleCtx = createContext<Ctx>({ vehicles: [], vehicle: null, setVehicleId: () => {}, loading: true });
const KEY = "motoq.vehicleId";

function readStored(): number | null {
  try {
    const v = localStorage.getItem(KEY);
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}

export function VehicleProvider({ children }: { children: ReactNode }) {
  const q = useQuery({ queryKey: ["vehicles"], queryFn: api.vehicles });
  const [id, setId] = useState<number | null>(readStored);
  const vehicles = q.data ?? [];
  const vehicle = vehicles.find((v) => v.id === id) ?? vehicles[0] ?? null;

  useEffect(() => {
    try {
      if (vehicle) localStorage.setItem(KEY, String(vehicle.id));
    } catch { /* 無痕模式等情況略過 */ }
  }, [vehicle?.id]);

  const value = useMemo(
    () => ({ vehicles, vehicle, setVehicleId: setId, loading: q.isLoading }),
    [vehicles, vehicle, q.isLoading],
  );
  return <VehicleCtx.Provider value={value}>{children}</VehicleCtx.Provider>;
}
export const useVehicle = () => useContext(VehicleCtx);
