import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api, type EnergyLogInput, type EnergySource } from "../api";
import Attachments from "../components/Attachments";
import { ConfirmButton, ErrorText, Field, PageTitle } from "../components/ui";
import { OTHER_STATION, SOURCES_BY_ENERGY, SOURCE_LABEL, STATION_BRANDS, isElectricSource, nf, today, toNum } from "../lib";
import { useVehicle } from "../vehicleContext";

type K = "q" | "p" | "t";

/** 三個數值（量、單價、總額）只要填兩個，第三個自動算出 */
function derive(v: Record<K, string>, touched: K[]): Record<K, string> {
  if (touched.length < 2) return v;
  const auto = (["q", "p", "t"] as K[]).find((k) => !touched.includes(k))!;
  const q = toNum(v.q), p = toNum(v.p), t = toNum(v.t);
  const out = { ...v };
  if (auto === "t" && q != null && p != null) out.t = String(Math.round(q * p));
  if (auto === "p" && q && t != null) out.p = (t / q).toFixed(1);
  if (auto === "q" && p && t != null) out.q = (t / p).toFixed(2);
  return out;
}

export default function EnergyForm() {
  const { id } = useParams();
  const editingId = id ? Number(id) : null;
  const { vehicle } = useVehicle();
  const nav = useNavigate();
  const qc = useQueryClient();
  const vid = vehicle?.id;

  const defaults = useQuery({ queryKey: ["defaults", vid], queryFn: () => api.defaults(vid!), enabled: !!vid && !editingId });
  const logs = useQuery({ queryKey: ["logs", vid], queryFn: () => api.logs(vid!), enabled: !!vid && !!editingId });
  const editing = useMemo(() => logs.data?.find((l) => l.id === editingId), [logs.data, editingId]);

  const [date, setDate] = useState(today());
  const [odoMode, setOdoMode] = useState<"reading" | "trip">("reading");
  const [odo, setOdo] = useState("");
  const [vals, setVals] = useState<Record<K, string>>({ q: "", p: "", t: "" });
  const [touched, setTouched] = useState<K[]>([]);
  const [isFull, setIsFull] = useState(true);
  const [missed, setMissed] = useState(false);
  const [source, setSource] = useState<EnergySource>("gas_95");
  const [stationChoice, setStationChoice] = useState<string>("中油");
  const [customStation, setCustomStation] = useState("");
  const [priceMode, setPriceMode] = useState<"auto" | "manual">("auto");
  const [startSoc, setStartSoc] = useState("");
  const [endSoc, setEndSoc] = useState("");
  const [note, setNote] = useState("");
  const [loaded, setLoaded] = useState(false);

  const electric = isElectricSource(source);
  const unit = electric ? "kWh" : "L";
  // 加油站：燃油用品牌下拉（可選其他自行輸入）；充電則是自由文字（站點或業者名稱）
  const station = electric || stationChoice === OTHER_STATION ? customStation.trim() : stationChoice;
  const loadStation = (name: string) => {
    if (!name || (STATION_BRANDS as readonly string[]).includes(name)) {
      setStationChoice(name || "中油");
      setCustomStation("");
    } else {
      setStationChoice(OTHER_STATION);
      setCustomStation(name);
    }
  };

  useEffect(() => {
    if (loaded) return;
    if (editing) {
      setDate(editing.log_date);
      setOdo(String(editing.odometer_km));
      setVals({ q: String(editing.quantity), p: String(editing.unit_price), t: String(editing.total_amount) });
      setTouched(["q", "p"]);
      setIsFull(editing.is_full);
      setMissed(editing.missed_before);
      setSource(editing.energy_source);
      loadStation(editing.station);
      setPriceMode("manual");
      setStartSoc(editing.start_soc?.toString() ?? "");
      setEndSoc(editing.end_soc?.toString() ?? "");
      setNote(editing.note);
      setLoaded(true);
    } else if (defaults.data && !editingId) {
      const d = defaults.data;
      setSource(d.energy_source);
      loadStation(d.station);
      setLoaded(true);
    }
  }, [editing, defaults.data, editingId, loaded]);

  // 依油品＋加油站取得建議單價（中油牌價／你在該站的實付價），換油品或加油站時自動更新
  const suggestion = useQuery({
    queryKey: ["priceSuggestion", vid, source, station],
    queryFn: () => api.priceSuggestion(vid!, source, station),
    enabled: !!vid && loaded && !editingId,
  });
  useEffect(() => {
    const price = suggestion.data?.price;
    if (price == null || priceMode !== "auto" || editingId) return;
    if (touched.length === 2 && !touched.includes("p")) return; // 單價是由數量與總額推算出來的，不覆蓋
    const nt: K[] = touched.includes("p") ? touched : [...touched, "p"];
    setTouched(nt);
    setVals((v) => derive({ ...v, p: String(price) }, nt));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggestion.data]);

  const lastReading = defaults.data?.last_odometer_km ?? 0;
  const reading = odoMode === "trip" ? lastReading + (toNum(odo) ?? 0) : toNum(odo);

  const setField = (k: K, value: string) => {
    if (k === "p") setPriceMode("manual");
    const nextTouched = [k, ...touched.filter((x) => x !== k)].slice(0, 2) as K[];
    setTouched(nextTouched);
    setVals(derive({ ...vals, [k]: value }, nextTouched));
  };
  const isAuto = (k: K) => touched.length === 2 && !touched.includes(k);

  // 換油品／電力時，單價與單位不同：清掉舊單價並回到自動帶入，由建議單價重新填入
  const changeSource = (s: EnergySource) => {
    const crossing = isElectricSource(s) !== isElectricSource(source);
    setSource(s);
    if (editingId) return;
    setPriceMode("auto");
    if (crossing) {
      setVals({ q: "", p: "", t: "" });
      setTouched([]);
    } else if (touched.includes("p") && !(touched.length === 2 && !touched.includes("p"))) {
      setVals((v) => ({ ...v, p: "" }));
    }
    if (crossing) setCustomStation("");
  };
  const applySuggestion = () => {
    const price = suggestion.data?.price;
    if (price == null) return;
    setPriceMode("auto");
    const nt: K[] = touched.includes("p") ? touched : [...touched.slice(-1), "p"];
    setTouched(nt);
    setVals((v) => derive({ ...v, p: String(price) }, nt));
  };

  const buildBody = (): EnergyLogInput => ({
    log_date: date,
    odometer_km: reading ?? 0,
    quantity: toNum(vals.q),
    unit_price: toNum(vals.p),
    total_amount: toNum(vals.t) != null ? Math.round(toNum(vals.t)!) : null,
    is_full: isFull,
    missed_before: missed,
    energy_source: source,
    station,
    start_soc: electric ? toNum(startSoc) : null,
    end_soc: electric ? toNum(endSoc) : null,
    note: note.trim(),
  });

  const save = useMutation({
    mutationFn: async (force: boolean) => {
      const body = buildBody();
      const send = (f: boolean) =>
        editingId ? api.updateLog(editingId, body, f) : api.createLog(vid!, body, f);
      try {
        return await send(force);
      } catch (e) {
        if (e instanceof ApiError && e.status === 409 && !force) {
          const msg = (e.detail as { message?: string })?.message ?? "里程小於先前記錄";
          if (window.confirm(`${msg}\n\n若是更換過儀表，請先到「車輛」設定里程表更換。仍要儲存嗎？`)) {
            return await send(true);
          }
        }
        throw e;
      }
    },
    onSuccess: (log) => {
      qc.invalidateQueries();
      const eff = log.efficiency != null ? `，本次 ${nf(log.efficiency, 1)} km/${log.unit}` : "";
      nav("/", { state: { flash: `已儲存 ${log.log_date}・$${nf(log.total_amount)}${eff}` }, replace: true });
    },
  });

  const remove = useMutation({
    mutationFn: () => api.deleteLog(editingId!),
    onSuccess: () => {
      qc.invalidateQueries();
      nav("/logs", { replace: true });
    },
  });

  if (!vehicle) return <p className="text-center text-slate-500">請先新增車輛</p>;
  if (editingId && logs.isLoading) return <p className="text-center text-slate-500">載入中…</p>;
  if (editingId && !editing) return <p className="text-center text-slate-500">找不到這筆記錄</p>;

  const ready = reading != null && (toNum(vals.q) ?? 0) > 0 && toNum(vals.t) != null;
  const sources = SOURCES_BY_ENERGY[vehicle.energy_type];
  const fullLabel = electric ? "已充滿" : "已加滿";

  return (
    <div className="space-y-4">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(false); }}>
        <PageTitle>{editingId ? "編輯記錄" : electric ? "新增充電" : "新增加油"}</PageTitle>

        <div className="grid grid-cols-2 gap-3 items-start">
          <Field label="日期">

            <input className="input" type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} required />
          </Field>
          <Field
            label={odoMode === "reading" ? "目前里程" : "本次里程"}
            hint={odoMode === "trip" && reading != null ? `= ${nf(reading)} km` : "km"}
          >
            <input className="input tabular-nums" inputMode="numeric" value={odo} autoFocus
              placeholder={odoMode === "reading" && lastReading ? `上次 ${nf(lastReading)}` : ""}
              onChange={(e) => setOdo(e.target.value.replace(/[^\d]/g, ""))} required />
          </Field>
        </div>

        {!editingId && (
          <button type="button" className="text-sm underline gold-text"
            onClick={() => { setOdoMode(odoMode === "reading" ? "trip" : "reading"); setOdo(""); }}>
            {odoMode === "reading" ? "改輸入單次里程 (trip)" : "改輸入總里程"}
          </button>
        )}

        <div className="grid grid-cols-3 gap-2">
          <Field label={unit} hint={isAuto("q") ? "自動" : undefined}>
            <input className="input tabular-nums" inputMode="decimal" value={vals.q}
              onChange={(e) => setField("q", e.target.value)} />
          </Field>
          <Field label={`單價/${unit}`} hint={isAuto("p") ? "自動" : undefined}>
            <input className="input tabular-nums" inputMode="decimal" value={vals.p}
              onChange={(e) => setField("p", e.target.value)} />
          </Field>
          <Field label="總額 $" hint={isAuto("t") ? "自動" : undefined}>
            <input className="input tabular-nums" inputMode="numeric" value={vals.t}
              onChange={(e) => setField("t", e.target.value)} />
          </Field>
        </div>
        <div className="-mt-2 space-y-1 text-xs text-slate-500">
          <p>三項填兩項，第三項自動計算。</p>
          {!editingId && suggestion.data?.price != null && (
            <p className="gold-text">
              單價參考：{suggestion.data.note}（{nf(suggestion.data.price, 1)} 元）
              {priceMode === "manual" && Number(vals.p) !== suggestion.data.price && (
                <button type="button" className="ml-2 underline" onClick={applySuggestion}>套用</button>
              )}
            </p>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label={vehicle.energy_type === "hybrid" ? "油品／充電" : electric ? "充電方式" : "油品"}>
            <select className="input" value={source} onChange={(e) => changeSource(e.target.value as EnergySource)}>
              {sources.map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}
            </select>
          </Field>
          {electric ? (
            <Field label="站點／業者">
              <input className="input" value={customStation} placeholder="例：家裡、Gogoro 站" onChange={(e) => setCustomStation(e.target.value)} />
            </Field>
          ) : (
            <Field label="加油站">
              <select className="input" value={stationChoice} onChange={(e) => { setStationChoice(e.target.value); if (!editingId) setPriceMode("auto"); }}>
                {STATION_BRANDS.map((b) => <option key={b} value={b}>{b}</option>)}
                <option value={OTHER_STATION}>其他（自行輸入）</option>
              </select>
            </Field>
          )}
          {!electric && stationChoice === OTHER_STATION && (
            <Field label="加油站名稱" className="col-span-2">
              <input className="input" value={customStation} onChange={(e) => setCustomStation(e.target.value)} />
            </Field>
          )}
        </div>

        {vehicle.energy_type === "hybrid" && electric && (
          <p className="rounded-xl bg-slate-100 px-3 py-2 text-xs text-slate-500 dark:bg-slate-900">
            油電車的 km/L 只以加油記錄計算；插電充電會計入費用，但不影響油耗。
          </p>
        )}

        <label className="card flex items-center justify-between">
          <span>
            <span className="font-medium">{fullLabel}</span>
            <span className="block text-xs text-slate-500">計算{electric ? "電耗" : "油耗"}需要前後兩次都是{fullLabel.slice(1)}</span>
          </span>
          <input type="checkbox" className="h-6 w-6 accent-brand-500" checked={isFull} onChange={(e) => setIsFull(e.target.checked)} />
        </label>

        <details className="card">
          <summary className="cursor-pointer font-medium">進階</summary>
          <div className="mt-3 space-y-3">
            {electric && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="充電前電量 %">
                  <input className="input" inputMode="numeric" value={startSoc} onChange={(e) => setStartSoc(e.target.value)} />
                </Field>
                <Field label="充電後電量 %">
                  <input className="input" inputMode="numeric" value={endSoc} onChange={(e) => setEndSoc(e.target.value)} />
                </Field>
              </div>
            )}
            <label className="flex items-center gap-3">
              <input type="checkbox" className="h-5 w-5 accent-brand-500" checked={missed} onChange={(e) => setMissed(e.target.checked)} />
              <span className="text-sm">這筆之前漏記了一次（該區間不納入油耗計算）</span>
            </label>
            <Field label="備註">
              <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
            </Field>
          </div>
        </details>

        <ErrorText error={save.error ?? remove.error} />

        <button className="btn-primary w-full" disabled={!ready || save.isPending}>
          {save.isPending ? "儲存中…" : "儲存"}
        </button>
        {editingId && (
          <ConfirmButton onConfirm={() => remove.mutate()} className="btn-danger w-full" confirmLabel="再按一次確認刪除">
            刪除這筆記錄
          </ConfirmButton>
        )}
      </form>

      {editingId && <Attachments ownerType="energy_log" ownerId={editingId} title="加油／充電單據" />}
    </div>
  );
}
