import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, type ServiceVisitInput } from "../api";
import Attachments from "../components/Attachments";
import { ConfirmButton, ErrorText, Field, PageTitle } from "../components/ui";
import { money, nf, today, toNum } from "../lib";
import { useVehicle } from "../vehicleContext";

interface Line { item_id: number | null; description: string; part_name: string; cost: string }
const blank = (): Line => ({ item_id: null, description: "", part_name: "", cost: "" });

export default function ServiceForm() {
  const { id } = useParams();
  const editingId = id ? Number(id) : null;
  const [sp] = useSearchParams();
  const presetItem = sp.get("item") ? Number(sp.get("item")) : null;
  const { vehicle } = useVehicle();
  const vid = vehicle?.id;
  const nav = useNavigate();
  const qc = useQueryClient();

  const items = useQuery({ queryKey: ["maintItems", vid], queryFn: () => api.maintItems(vid!), enabled: !!vid });
  const visits = useQuery({ queryKey: ["visits", vid], queryFn: () => api.visits(vid!), enabled: !!vid && !!editingId });
  const defaults = useQuery({ queryKey: ["defaults", vid], queryFn: () => api.defaults(vid!), enabled: !!vid && !editingId });
  const existing = visits.data?.find((v) => v.id === editingId);

  const [date, setDate] = useState(today());
  const [odo, setOdo] = useState("");
  const [shop, setShop] = useState("");
  const [note, setNote] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [totalOverride, setTotalOverride] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (ready) return;
    if (existing) {
      setDate(existing.visit_date);
      setOdo(String(existing.odometer_km));
      setShop(existing.shop);
      setNote(existing.technician_note);
      setLines(existing.lines.map((l) => ({
        item_id: l.item_id, description: l.description, part_name: l.part_name, cost: String(l.cost),
      })));
      const sum = existing.lines.reduce((s, l) => s + l.cost, 0);
      if (existing.total_cost !== sum) setTotalOverride(String(existing.total_cost));
      setReady(true);
    } else if (!editingId && defaults.data) {
      setOdo(String(defaults.data.last_odometer_km || ""));
      setLines([{ ...blank(), item_id: presetItem }]);
      setReady(true);
    }
  }, [existing, defaults.data, editingId, presetItem, ready]);

  const sum = lines.reduce((s, l) => s + (toNum(l.cost) ?? 0), 0);
  const setLine = (i: number, patch: Partial<Line>) =>
    setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  const save = useMutation({
    mutationFn: () => {
      const body: ServiceVisitInput = {
        visit_date: date, odometer_km: toNum(odo) ?? 0, shop: shop.trim(), technician_note: note.trim(),
        total_cost: toNum(totalOverride),
        lines: lines
          .filter((l) => l.item_id || l.description.trim() || l.part_name.trim())
          .map((l) => ({ item_id: l.item_id, description: l.description.trim(), part_name: l.part_name.trim(), cost: toNum(l.cost) ?? 0 })),
      };
      return editingId ? api.updateVisit(editingId, body) : api.createVisit(vid!, body);
    },
    onSuccess: (v) => {
      qc.invalidateQueries();
      // 新增後留在此頁，方便接著附上單據照片
      if (!editingId) nav(`/service/${v.id}`, { replace: true });
      else nav("/service", { replace: true });
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteVisit(editingId!),
    onSuccess: () => { qc.invalidateQueries(); nav("/service", { replace: true }); },
  });

  if (!vehicle) return <p className="text-center text-slate-500">請先新增車輛</p>;
  if (editingId && visits.isLoading) return <p className="text-center text-slate-500">載入中…</p>;
  if (editingId && !existing) return <p className="text-center text-slate-500">找不到這筆記錄</p>;

  return (
    <div className="space-y-4">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <PageTitle>{editingId ? "編輯進廠記錄" : "記錄保養／維修"}</PageTitle>
        <div className="grid grid-cols-2 gap-3 items-start">
          <Field label="日期"><input className="input" type="date" max={today()} value={date} onChange={(e) => setDate(e.target.value)} required /></Field>

          <Field label="里程" hint="km"><input className="input tabular-nums" inputMode="numeric" value={odo} onChange={(e) => setOdo(e.target.value.replace(/[^\d]/g, ""))} required /></Field>
        </div>

        <Field label="車行／技師（自行更換可留空）"><input className="input" value={shop} onChange={(e) => setShop(e.target.value)} /></Field>

        <section className="space-y-3">
          <h2 className="text-base font-semibold">項目明細</h2>
          {lines.map((l, i) => (
            <div key={i} className="card space-y-2">
              <select className="input" value={l.item_id ?? ""} onChange={(e) => setLine(i, { item_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">一次性維修（不對應保養項目）</option>
                {items.data?.map((it) => <option key={it.id} value={it.id}>{it.name}</option>)}
              </select>
              <input className="input" placeholder="說明（例：更換前煞車皮）" value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} />
              <div className="grid grid-cols-3 gap-2">
                <input className="input col-span-2" placeholder="零件／品牌" value={l.part_name} onChange={(e) => setLine(i, { part_name: e.target.value })} />
                <input className="input tabular-nums" inputMode="numeric" placeholder="費用" value={l.cost} onChange={(e) => setLine(i, { cost: e.target.value })} />
              </div>
              {lines.length > 1 && (
                <button type="button" className="text-xs text-red-500" onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}>移除此列</button>
              )}
            </div>
          ))}
          <button type="button" className="btn-ghost w-full" onClick={() => setLines((ls) => [...ls, blank()])}>＋ 增加一列</button>
        </section>

        <div className="card flex items-center justify-between">
          <span className="text-sm text-slate-500">明細合計</span>
          <span className="font-serif text-xl font-semibold tabular-nums">{money(sum)}</span>
        </div>
        <Field label="實付總額（含工資等，不填則用明細合計）">
          <input className="input tabular-nums" inputMode="numeric" value={totalOverride} placeholder={nf(sum)} onChange={(e) => setTotalOverride(e.target.value)} />
        </Field>
        <Field label="技師備註"><textarea className="input min-h-[80px]" value={note} onChange={(e) => setNote(e.target.value)} /></Field>

        <ErrorText error={save.error ?? remove.error} />
        <button className="btn-primary w-full" disabled={save.isPending}>{save.isPending ? "儲存中…" : "儲存"}</button>
        {editingId && <ConfirmButton onConfirm={() => remove.mutate()} className="btn-danger w-full" confirmLabel="再按一次確認刪除">刪除這筆記錄</ConfirmButton>}
      </form>

      {editingId ? (
        <Attachments ownerType="service_visit" ownerId={editingId} title="保養工單／收據" />
      ) : (
        <p className="text-center text-xs text-slate-500">儲存後即可附上工單照片。</p>
      )}
    </div>
  );
}
