import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ApiError, api } from "./api";
import Layout from "./components/Layout";
import Auth from "./pages/Auth";
import Compliance from "./pages/Compliance";
import Dashboard from "./pages/Dashboard";
import EnergyForm from "./pages/EnergyForm";
import Expenses from "./pages/Expenses";
import Logs from "./pages/Logs";
import Maintenance from "./pages/Maintenance";
import More from "./pages/More";
import Service from "./pages/Service";
import ServiceForm from "./pages/ServiceForm";
import Settings from "./pages/Settings";
import VehicleForm from "./pages/VehicleForm";
import Vehicles from "./pages/Vehicles";
import { VehicleProvider } from "./vehicleContext";

const Admin = lazy(() => import("./pages/Admin"));
const Reports = lazy(() => import("./pages/Reports"));

export default function App() {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });

  if (me.isLoading) return <div className="p-8 text-center text-slate-500">載入中…</div>;
  if (me.error instanceof ApiError && me.error.status === 401) return <Auth />;
  if (me.error) return <div className="p-8 text-center text-red-600">無法連線到伺服器</div>;
  const isAdmin = me.data?.role === "admin";

  return (
    <VehicleProvider>
      <Layout>
        <Suspense fallback={<p className="text-center text-slate-500">載入中…</p>}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/add" element={<EnergyForm />} />
          <Route path="/logs" element={<Logs />} />
          <Route path="/logs/:id/edit" element={<EnergyForm />} />
          <Route path="/maintenance" element={<Maintenance />} />
          <Route path="/service" element={<Service />} />
          <Route path="/service/new" element={<ServiceForm />} />
          <Route path="/service/:id" element={<ServiceForm />} />
          <Route path="/compliance" element={<Compliance />} />
          <Route path="/expenses" element={<Expenses />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/more" element={<More me={me.data!} />} />
          <Route path="/vehicles" element={<Vehicles />} />
          <Route path="/vehicles/new" element={<VehicleForm />} />
          <Route path="/vehicles/:id" element={<VehicleForm />} />
          <Route path="/settings" element={<Settings me={me.data!} />} />
          <Route path="/admin" element={isAdmin ? <Admin /> : <Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </Layout>
    </VehicleProvider>
  );
}
