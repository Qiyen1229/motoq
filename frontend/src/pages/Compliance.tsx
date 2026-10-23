import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Compliance as C, type ComplianceKind } from "../api";
import Attachments from "../components/Attachments";
import OfficialLinks from "../components/OfficialLinks";
import { Chip, ConfirmButton, Empty, ErrorText, Field, PageTitle } from "../components/ui";
import { COMPLIANCE_LABEL, money, today, toNum } from "../lib";
import { useVehicle } from "../vehicleContext";

const REC_DEFAULT: Partial<Record<ComplianceKind, number>> = {
  license_tax: 12, fuel_fee: 12, compulsory_ins: 12, voluntary_ins: 12, inspection: 12, emission_test: 12,
};

function badge(c: C) {
  if (c.state === "paid") return <Chip tone="green">已繳 {c.paid_date}</Chip>;
  if (c.state === "overdue") return <Chip tone="red">逾期 {-c.days_left} 天</Chip>;
  if (c.state === "due_soon") return <Chip tone={c.level >= 2 ? "red" : "amber"}>{c.days_left === 0 ? "今天到期" : `剩 ${c.days_left} 天`}</Chip>;
  return <Chip>剩 {c.days_left} 天</Chip>;
}

export default function Compliance() {
  const { vehicle } = useVehicle();
  const vid = vehicle?.id;
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["compliance", vid], queryFn: () => api.compliance(vid!), enabled: !!vid });
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<number | null>(null);

  const refresh = () => { qc.invalidateQueries({ queryKey: ["compliance"] }); qc.invalidateQueries({ queryKey: ["attention"] }); };
  const estimate = useQuery({ queryKey: ["complianceEstimate", vid], queryFn: () => api.complianceEstimate(vid!), enabled: !!vid });
  const createTax = useMutation({
    mutationFn: () => {
      const t = estimate.data!.license_tax;
      return api.createCompliance(vid!, {
        kind: "license_tax", due_date: t.due_date, amount: t.amount ?? 0, paid_date: null,
        provider: "", policy_no: "", recurrence_months: 12, note: t.exempt ? "免徵" : "",
      });
    },
    onSuccess: () => { refresh(); qc.invalidateQueries({ queryKey: ["complianceEstimate"] }); },
  });
  const pay = useMutation({ mutationFn: (id: number) => api.payCompliance(id, { create_next: true }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (id: number) => api.deleteCompliance(id), onSuccess: refresh });

  if (!vehicle) return <Empty>請先新增車輛</Empty>;
  const unpaid = (list.data ?? []).filter((c) => c.state !== "paid");
  const paid = (list.data ?? []).filter((c) => c.state === "paid");

  const row = (c: C) => (
    <li key={c.id} className="card space-y-2">
      <button className="flex w-full items-start justify-between gap-3 text-left" onClick={() => setOpen(open === c.id ? null : c.id)}>
        <div>
          <div className="font-semibold">{c.kind_label}</div>
          <div className="text-xs text-slate-500">
            到期 {c.due_date}{c.amount ? `・${money(c.amount)}` : ""}{c.provider ? `・${c.provider}` : ""}
          </div>
        </div>
        {badge(c)}
      </button>
      {open === c.id && (
        <div className="space-y-3 border-t border-slate-200 pt-3 dark:border-slate-800">
          {c.policy_no && <p className="text-xs text-slate-500">保單號碼：{c.policy_no}</p>}
          {c.note && <p className="text-sm">{c.note}</p>}
          <div className="flex flex-wrap justify-end gap-2">
            {c.state !== "paid" && (
              <button className="btn-primary btn-sm" disabled={pay.isPending} onClick={() => pay.mutate(c.id)}>
                標記已繳（並建立下一期）
              </button>
            )}
            <ConfirmButton onConfirm={() => remove.mutate(c.id)}>刪除</ConfirmButton>
          </div>
          <Attachments ownerType="compliance_item" ownerId={c.id} title="保單／繳費收據" />
        </div>
      )}
    </li>
  );

  return (
    <div className="space-y-4">
      <PageTitle action={<button className="btn-primary btn-sm" onClick={() => setAdding(!adding)}>{adding ? "取消" : "＋ 新增"}</button>}>
        稅費與到期
      </PageTitle>
      {estimate.data && !estimate.data.license_tax.already_created && (
        <section className="card space-y-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="label !mb-0">牌照稅（依車輛資料估算）</div>
              <div className="font-serif text-2xl font-semibold tabular-nums">
                {estimate.data.license_tax.exempt ? "免徵" : estimate.data.license_tax.amount != null ? money(estimate.data.license_tax.amount) : "—"}
              </div>
              <div className="text-xs text-slate-500">{estimate.data.license_tax.note}</div>
              <div className="text-xs text-slate-500">繳納期限 {estimate.data.license_tax.due_date}（每年 4 月）</div>
            </div>
          </div>
          <button className="btn-primary w-full" disabled={createTax.isPending || estimate.data.license_tax.amount == null}
            onClick={() => createTax.mutate()}>
            一鍵建立今年的牌照稅提醒
          </button>
          <ErrorText error={createTax.error} />
        </section>
      )}
      {adding && vid && <ComplianceForm vehicleId={vid} onDone={() => { setAdding(false); refresh(); }} />}
      <ErrorText error={pay.error ?? remove.error} />
      {list.data?.length === 0 && !adding && <Empty>尚無資料。可新增牌照稅、燃料費、強制險、任意險、驗車與排氣檢驗的到期日。</Empty>}
      <OfficialLinks topic="tax" />
      {unpaid.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">待繳／待辦</h2>
          <ul className="space-y-2">{unpaid.map(row)}</ul>
        </section>
      )}
      {paid.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">已完成</h2>
          <ul className="space-y-2 opacity-90">{paid.map(row)}</ul>
        </section>
      )}
    </div>
  );
}

function ComplianceForm({ vehicleId, onDone }: { vehicleId: number; onDone: () => void }) {
  const [kind, setKind] = useState<ComplianceKind>("license_tax");
  const [due, setDue] = useState("");
  const [amount, setAmount] = useState("");
  const [provider, setProvider] = useState("");
  const [policy, setPolicy] = useState("");
  const [rec, setRec] = useState("12");
  const insurance = kind === "compulsory_ins" || kind === "voluntary_ins";
  const create = useMutation({
    mutationFn: () => api.createCompliance(vehicleId, {
      kind, due_date: due, amount: toNum(amount) ?? 0, paid_date: null,
      provider: provider.trim(), policy_no: policy.trim(), recurrence_months: toNum(rec), note: "",
    }),
    onSuccess: onDone,
  });
  return (
    <form className="card space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="類別">
          <select className="input" value={kind} onChange={(e) => { const k = e.target.value as ComplianceKind; setKind(k); setRec(String(REC_DEFAULT[k] ?? "")); }}>
            {Object.entries(COMPLIANCE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </Field>
        <Field label="到期日"><input className="input" type="date" value={due} onChange={(e) => setDue(e.target.value)} required /></Field>
        <Field label="金額 $（選填）"><input className="input" inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="週期（月）"><input className="input" inputMode="numeric" value={rec} onChange={(e) => setRec(e.target.value)} /></Field>
        {insurance && <Field label="保險公司"><input className="input" value={provider} onChange={(e) => setProvider(e.target.value)} /></Field>}
        {insurance && <Field label="保單號碼"><input className="input" value={policy} onChange={(e) => setPolicy(e.target.value)} /></Field>}
      </div>
      <ErrorText error={create.error} />
      <button className="btn-primary w-full" disabled={create.isPending || !due}>新增</button>
    </form>
  );
}
