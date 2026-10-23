import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, type EnergySource, type EnergyType, type VehicleInput, type VehicleType } from "../api";
import { ConfirmButton, ErrorText, Field, PageTitle } from "../components/ui";
import { ENERGY_TYPE_LABEL, SOURCES_BY_ENERGY, SOURCE_LABEL, VEHICLE_TYPE_LABEL, nf, today, toNum } from "../lib";

const EMPTY: VehicleInput = {
  vehicle_type: "scooter", energy_type: "gasoline", brand: "", model: "", plate: "",
  displacement_cc: null, battery_kwh: null, default_energy_source: "gas_95",
  purchase_date: null, purchase_price: null, initial_odometer_km: 0,
  status: "active", sold_date: null, sold_price: null,
};
const defaultSource = (e: EnergyType): EnergySource => (e === "electric" ? "home" : "gas_95");

export default function VehicleForm() {
  const { id } = useParams();
  const vid = id ? Number(id) : null;
  const nav = useNavigate();
  const qc = useQueryClient();
  const [form, setForm] = useState<VehicleInput>(EMPTY);

  const vehicles = useQuery({ queryKey: ["vehicles"], queryFn: api.vehicles });
  const existing = vehicles.data?.find((v) => v.id === vid);
  useEffect(() => {
    if (existing) {
      const { id: _id, current_odometer_km: _c, ...rest } = existing;
      setForm(rest);
    }
  }, [existing?.id]);

  const set = <K extends keyof VehicleInput>(k: K, v: VehicleInput[K]) => setForm((f) => ({ ...f, [k]: v }));
  const setEnergy = (e: EnergyType) =>
    setForm((f) => ({ ...f, energy_type: e, default_energy_source: defaultSource(e) }));
  const setType = (t: VehicleType) =>
    setForm((f) => {
      const hybridOk = t === "car";
      const energy = f.energy_type === "hybrid" && !hybridOk ? "gasoline" : f.energy_type;
      return { ...f, vehicle_type: t, energy_type: energy, default_energy_source: energy === f.energy_type ? f.default_energy_source : defaultSource(energy) };
    });

  const save = useMutation({
    mutationFn: () => (vid ? api.updateVehicle(vid, form) : api.createVehicle(form)),
    onSuccess: () => { qc.invalidateQueries(); nav("/vehicles", { replace: true }); },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteVehicle(vid!),
    onSuccess: () => { qc.invalidateQueries(); nav("/vehicles", { replace: true }); },
  });

  const energyOptions = (Object.keys(ENERGY_TYPE_LABEL) as EnergyType[]).filter(
    (e) => e !== "hybrid" || form.vehicle_type === "car",
  );
  const hasBattery = form.energy_type !== "gasoline";

  return (
    <div className="space-y-4">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <PageTitle>{vid ? "編輯車輛" : "新增車輛"}</PageTitle>
        <div className="grid grid-cols-2 gap-3">
          <Field label="車種">
            <select className="input" value={form.vehicle_type} onChange={(e) => setType(e.target.value as VehicleType)}>
              {Object.entries(VEHICLE_TYPE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </Field>
          <Field label="能源" hint={form.vehicle_type === "car" ? undefined : "油電僅限汽車"}>
            <select className="input" value={form.energy_type} onChange={(e) => setEnergy(e.target.value as EnergyType)}>
              {energyOptions.map((k) => <option key={k} value={k}>{ENERGY_TYPE_LABEL[k]}</option>)}
            </select>
          </Field>
          <Field label="廠牌"><input className="input" value={form.brand} onChange={(e) => set("brand", e.target.value)} /></Field>
          <Field label="車型"><input className="input" value={form.model} onChange={(e) => set("model", e.target.value)} /></Field>
          <Field label="車牌"><input className="input" value={form.plate} onChange={(e) => set("plate", e.target.value.toUpperCase())} /></Field>
          {form.energy_type !== "electric" ? (
            <Field label="排氣量" hint="cc">
              <input className="input tabular-nums" inputMode="numeric" value={form.displacement_cc ?? ""} onChange={(e) => set("displacement_cc", toNum(e.target.value))} />
            </Field>
          ) : <div />}
          {hasBattery && (
            <Field label="電池容量" hint="kWh">
              <input className="input tabular-nums" inputMode="decimal" value={form.battery_kwh ?? ""} onChange={(e) => set("battery_kwh", toNum(e.target.value))} />
            </Field>
          )}
          <Field label="預設能源" hint={form.energy_type === "electric" ? "充電" : "油品"}>
            <select className="input" value={form.default_energy_source ?? ""} onChange={(e) => set("default_energy_source", e.target.value as EnergySource)}>
              {SOURCES_BY_ENERGY[form.energy_type].map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}
            </select>
          </Field>
          <Field label="初始里程" hint="km">
            <input className="input tabular-nums" inputMode="numeric" value={form.initial_odometer_km} onChange={(e) => set("initial_odometer_km", toNum(e.target.value) ?? 0)} />
          </Field>
          <Field label="購入日期">
            <input className="input" type="date" max={today()} value={form.purchase_date ?? ""} onChange={(e) => set("purchase_date", e.target.value || null)} />
          </Field>
          <Field label="購入價格" hint="元">
            <input className="input tabular-nums" inputMode="numeric" value={form.purchase_price ?? ""} onChange={(e) => set("purchase_price", toNum(e.target.value))} />
          </Field>

          <Field label="狀態">
            <select className="input" value={form.status} onChange={(e) => set("status", e.target.value as "active" | "sold")}>
              <option value="active">使用中</option>
              <option value="sold">已賣出</option>
            </select>
          </Field>
          {form.status === "sold" && (
            <Field label="賣出日期">
              <input className="input" type="date" value={form.sold_date ?? ""} onChange={(e) => set("sold_date", e.target.value || null)} />
            </Field>
          )}
        </div>
        {form.energy_type === "hybrid" && (
          <p className="rounded-xl bg-slate-100 px-3 py-2 text-xs text-slate-500 dark:bg-slate-900">
            油電車：km/L 以加油記錄計算；若為插電式，充電可選「家用充電」等來源，費用會計入但不影響油耗。
          </p>
        )}
        <ErrorText error={save.error ?? remove.error} />
        <button className="btn-primary w-full" disabled={save.isPending}>{save.isPending ? "儲存中…" : "儲存"}</button>
        {vid && (
          <ConfirmButton onConfirm={() => remove.mutate()} className="btn-danger w-full" confirmLabel="再按一次確認刪除車輛">
            刪除車輛
          </ConfirmButton>
        )}
      </form>
      {vid && <Adjustments vehicleId={vid} />}
    </div>
  );
}

function Adjustments({ vehicleId }: { vehicleId: number }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["adjustments", vehicleId], queryFn: () => api.adjustments(vehicleId) });
  const [date, setDate] = useState(today());
  const [offset, setOffset] = useState("");
  const [note, setNote] = useState("換儀表");
  const add = useMutation({
    mutationFn: () => api.addAdjustment(vehicleId, { effective_date: date, offset_km: Number(offset), note }),
    onSuccess: () => { setOffset(""); qc.invalidateQueries(); },
  });
  const del = useMutation({ mutationFn: (id: number) => api.deleteAdjustment(id), onSuccess: () => qc.invalidateQueries() });

  return (
    <section className="card space-y-3">
      <div>
        <h2 className="text-base font-semibold">里程表更換／歸零</h2>
        <p className="text-xs text-slate-500">換儀表或歸零後，填入「更換當下的舊總里程」，之後輸入新儀表讀數，總里程會自動接續。</p>
      </div>
      {list.data?.map((a) => (
        <div key={a.id} className="flex items-center justify-between rounded-xl bg-slate-100 px-3 py-2 text-sm dark:bg-slate-800">
          <span>{a.effective_date}・+{nf(a.offset_km)} km{a.note && `（${a.note}）`}</span>
          <ConfirmButton onConfirm={() => del.mutate(a.id)} className="btn-danger btn-sm !px-2">{""}</ConfirmButton>
        </div>
      ))}
      <div className="grid grid-cols-2 gap-2">
        <input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} aria-label="生效日期" />
        <input className="input" inputMode="numeric" placeholder="加上的里程 km" value={offset}
          onChange={(e) => setOffset(e.target.value.replace(/[^\d-]/g, ""))} />
      </div>
      <input className="input" placeholder="備註" value={note} onChange={(e) => setNote(e.target.value)} />
      <ErrorText error={add.error ?? del.error} />
      <button className="btn-ghost w-full" disabled={!offset || add.isPending} onClick={() => add.mutate()}>新增調整</button>
    </section>
  );
}
