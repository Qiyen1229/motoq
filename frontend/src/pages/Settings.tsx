import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type Me } from "../api";
import { ErrorText, Field, PageTitle, Tabs } from "../components/ui";
import { toNum } from "../lib";

type Theme = "dark" | "light" | "auto";
const getTheme = (): Theme => {
  try { return (localStorage.getItem("motoq.theme") as Theme) || "dark"; } catch { return "dark"; }
};
const applyTheme = (t: Theme) => {
  try { localStorage.setItem("motoq.theme", t); } catch { /* 無痕模式 */ }
  const dark = t === "dark" || (t === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#0c0c0b" : "#ffffff");
};

export default function Settings({ me }: { me: Me }) {
  const qc = useQueryClient();
  const [theme, setTheme] = useState<Theme>(getTheme);
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [pct, setPct] = useState("15");
  const [leads, setLeads] = useState("30, 7, 1");
  const [autoCheck, setAutoCheck] = useState(false);
  const [autoCities, setAutoCities] = useState<string[]>(["TPE"]);
  const [etagLow, setEtagLow] = useState("200");
  const cityList = useQuery({ queryKey: ["parkingCities"], queryFn: api.parkingCities, staleTime: Infinity });
  useEffect(() => {
    if (settings.data) {
      setPct(String(settings.data.anomaly_drop_pct));
      setLeads(settings.data.lead_days.join(", "));
      setAutoCheck(settings.data.parking_auto_check);
      setAutoCities(settings.data.parking_cities);
      setEtagLow(String(settings.data.etag_low_balance));
    }
  }, [settings.data]);
  const saveSettings = useMutation({
    mutationFn: () =>
      api.saveSettings({
        anomaly_drop_pct: toNum(pct) ?? 15,
        lead_days: leads.split(/[,\s、]+/).filter(Boolean).map(Number).filter((n) => Number.isInteger(n)),
        parking_auto_check: autoCheck,
        parking_cities: autoCities,
        etag_low_balance: toNum(etagLow) ?? 0,
      }),
    onSuccess: () => qc.invalidateQueries(),
  });

  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const preview = useMutation({ mutationFn: (f: File) => api.importData(f, true) });
  const doImport = useMutation({
    mutationFn: () => api.importData(file!, false),
    onSuccess: () => {
      qc.invalidateQueries();
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
    },
  });

  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const changePw = useMutation({ mutationFn: () => api.changePassword(cur, next), onSuccess: () => { setCur(""); setNext(""); } });
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => { qc.clear(); window.location.assign("/"); },
  });

  return (
    <div className="space-y-4">
      <PageTitle>設定</PageTitle>
      <p className="text-sm text-slate-500">{me.username}・{me.role === "admin" ? "管理員" : "一般使用者"}</p>

      <section className="card space-y-3">
        <h2 className="text-base font-semibold">外觀</h2>
        <Tabs<Theme> value={theme} onChange={(t) => { setTheme(t); applyTheme(t); }}
          tabs={[{ id: "dark", label: "黑金（深色）" }, { id: "light", label: "象牙（淺色）" }, { id: "auto", label: "跟隨系統" }]} />
      </section>

      <section className="card space-y-3">
        <h2 className="text-base font-semibold">提醒與警示</h2>
        <Field label="到期提前提醒天數（逗號分隔）">
          <input className="input" value={leads} onChange={(e) => setLeads(e.target.value)} placeholder="30, 7, 1" />
        </Field>
        <Field label="油耗異常：近 3 次低於先前基準 % 時警示">
          <input className="input" inputMode="decimal" value={pct} onChange={(e) => setPct(e.target.value)} />
        </Field>
        <Field label="etag 餘額低於多少元時列入待辦（0 = 不提醒）">
          <input className="input" inputMode="numeric" value={etagLow} onChange={(e) => setEtagLow(e.target.value)} />
        </Field>

        <div className="space-y-2 rounded-xl border border-slate-200 p-3 dark:border-slate-800">
          <label className="flex items-center justify-between gap-3">
            <span>
              <span className="block font-medium">每日自動檢查停車費欠費</span>
              <span className="block text-xs text-slate-500">
                每天早上自動查詢，有欠費會出現在首頁待辦。開啟後會把你車輛的車牌送到所選縣市政府的公開查詢服務。
              </span>
            </span>
            <input type="checkbox" className="h-6 w-6 shrink-0 accent-brand-500" checked={autoCheck} onChange={(e) => setAutoCheck(e.target.checked)} />
          </label>
          {autoCheck && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {(cityList.data ?? []).map((c) => {
                const on = autoCities.includes(c.code);
                return (
                  <button key={c.code} type="button"
                    onClick={() => setAutoCities(on ? autoCities.filter((x) => x !== c.code) : [...autoCities, c.code])}
                    className={`rounded-full border px-2.5 py-1 text-xs ${on ? "border-brand-500 bg-brand-500/15 text-brand-800 dark:text-brand-300" : "border-slate-300 text-slate-500 dark:border-slate-700"}`}>
                    {c.name}
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <ErrorText error={saveSettings.error} />
        <button className="btn-ghost w-full" disabled={saveSettings.isPending} onClick={() => saveSettings.mutate()}>
          {saveSettings.isSuccess ? "已儲存 ✓" : "儲存"}
        </button>
      </section>

      <section className="card space-y-3">
        <h2 className="text-base font-semibold">匯出／匯入</h2>
        <div className="grid grid-cols-2 gap-2">
          <a className="btn-ghost" href="/api/v1/data/export?format=json" download>匯出 JSON</a>
          <a className="btn-ghost" href="/api/v1/data/export?format=csv" download>匯出 CSV</a>
        </div>
        <p className="text-xs text-slate-500">匯出只含你的資料（不含單據照片檔案；照片請用伺服器的備份指令一併備份）。</p>
        <Field label="匯入 JSON（會取代你目前的全部資料，匯入前自動快照）">
          <input ref={fileRef} type="file" accept="application/json,.json" className="input"
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f);
              if (f) preview.mutate(f);
            }} />
        </Field>
        <ErrorText error={preview.error ?? doImport.error} />
        {preview.data && file && (
          <div className="space-y-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
            <p>將匯入：{Object.entries(preview.data.counts).filter(([, n]) => n > 0).map(([k, n]) => `${k} ${n} 筆`).join("、") || "（空檔案）"}</p>
            <button className="btn-primary w-full" disabled={doImport.isPending}
              onClick={() => window.confirm("確定以此檔案取代你目前所有資料？") && doImport.mutate()}>
              確認匯入
            </button>
          </div>
        )}
        {doImport.data && <p className="text-sm gold-text">匯入完成，已建立快照 {doImport.data.snapshot}</p>}
      </section>

      <section className="card space-y-3">
        <h2 className="text-base font-semibold">變更密碼</h2>
        <Field label="目前密碼">
          <input className="input" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} />
        </Field>
        <Field label="新密碼（至少 8 碼）">
          <input className="input" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
        </Field>
        <p className="text-xs text-slate-500">更新後，其他裝置的登入會被登出。</p>
        <ErrorText error={changePw.error} />
        <button className="btn-ghost w-full" disabled={!cur || next.length < 8 || changePw.isPending} onClick={() => changePw.mutate()}>
          {changePw.isSuccess ? "已更新 ✓" : "更新密碼"}
        </button>
      </section>

      <button className="btn-danger w-full" onClick={() => logout.mutate()}>登出</button>
    </div>
  );
}
