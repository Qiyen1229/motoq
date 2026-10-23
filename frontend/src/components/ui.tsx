import { useState, type ReactNode } from "react";
import Icon from "./Icon";

export function Field({ label, hint, children, className = "" }: {
  label: string; hint?: string; children: ReactNode; className?: string;
}) {
  return (
    <label className={`flex flex-col justify-start ${className}`}>
      <span className="label flex h-5 items-center justify-between gap-1 overflow-hidden">
        <span className="truncate leading-none">{label}</span>
        {hint && <span className="shrink-0 text-[11px] font-normal normal-case tracking-normal gold-text leading-none">{hint}</span>}
      </span>
      {children}
    </label>
  );
}


export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: string; tone?: "warn" }) {
  return (
    <div className={`card flex flex-col justify-between h-full min-h-[104px] ${tone === "warn" ? "ring-amber-500/50" : ""}`}>
      <div>
        <div className="label !mb-0 truncate">{label}</div>
        <div className="mt-1 font-serif text-[22px] sm:text-[26px] font-semibold leading-tight tabular-nums truncate">{value}</div>
      </div>
      <div className="mt-1.5 min-h-[16px] text-xs text-slate-500 leading-tight truncate" title={sub}>
        {sub || <span className="opacity-0 select-none">—</span>}
      </div>
    </div>
  );
}


export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/60 dark:text-red-300">
      {error instanceof Error ? error.message : "發生未知錯誤"}
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="card py-10 text-center text-sm text-slate-500">{children}</div>;
}

export function PageTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <h1 className="text-2xl font-semibold">{children}</h1>
      {action}
    </div>
  );
}

const CHIP_TONES = {
  gold: "bg-brand-500/15 text-brand-800 dark:text-brand-300",
  red: "bg-red-500/10 text-red-700 dark:text-red-300",
  amber: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  green: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  gray: "bg-slate-200/70 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
} as const;
export function Chip({ tone = "gray", children }: { tone?: keyof typeof CHIP_TONES; children: ReactNode }) {
  return <span className={`chip shrink-0 whitespace-nowrap ${CHIP_TONES[tone]}`}>{children}</span>;
}

export function Progress({ value, tone }: { value: number; tone: "ok" | "soon" | "overdue" }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  const color = tone === "overdue" ? "bg-red-500" : tone === "soon" ? "bg-amber-500" : "bg-brand-500";
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, tabs }: {
  value: T; onChange: (v: T) => void; tabs: { id: T; label: string }[];
}) {
  return (
    <div className="flex gap-1 rounded-xl bg-slate-200/60 p-1 dark:bg-slate-900" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={`flex-1 rounded-lg px-2 py-2 text-sm transition ${
            value === t.id
              ? "bg-white font-semibold shadow dark:bg-slate-800 dark:text-brand-400"
              : "text-slate-500"
          }`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

/** 先按一次出現「確認」，避免誤刪；比 window.confirm 在手機上更順手 */
export function ConfirmButton({ onConfirm, children, className = "btn-danger btn-sm", confirmLabel = "確定？" }: {
  onConfirm: () => void; children: ReactNode; className?: string; confirmLabel?: string;
}) {
  const [armed, setArmed] = useState(false);
  return armed ? (
    <button type="button" className={`${className} !bg-red-600 !text-white`}
      onClick={() => { setArmed(false); onConfirm(); }} onBlur={() => setArmed(false)} autoFocus>
      {confirmLabel}
    </button>
  ) : (
    <button type="button" className={className} onClick={() => setArmed(true)}>
      <Icon name="trash" className="h-4 w-4" />
      {children}
    </button>
  );
}
