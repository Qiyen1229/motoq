import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import { ErrorText, Field } from "../components/ui";

export default function Auth() {
  const qc = useQueryClient();
  const reg = useQuery({ queryKey: ["registration"], queryFn: api.registration });
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [token, setToken] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const firstRun = reg.data && !reg.data.has_users;
  const effective = firstRun ? "register" : mode;

  const login = useMutation({
    mutationFn: () => api.login(username, password),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
  const register = useMutation({
    mutationFn: () => {
      if (password !== confirm) throw new Error("兩次輸入的密碼不一致");
      return api.register(username, password, token);
    },
    onSuccess: (r) => {
      if (r.pending) {
        setNotice("註冊完成，帳號需等待管理員核准後才能登入。");
        setMode("login");
        setPassword("");
        setConfirm("");
      } else {
        qc.invalidateQueries({ queryKey: ["me"] });
      }
    },
  });
  const m = effective === "login" ? login : register;
  const closed = effective === "register" && !firstRun && reg.data?.can_register === false;

  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-8 px-6 py-10">
      <div className="text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full border border-brand-500/60 text-brand-400">
          <Icon name="moto" className="h-8 w-8" />
        </div>
        <h1 className="mt-4 text-3xl font-semibold tracking-[0.25em] text-brand-400">MOTOQ</h1>
        <p className="mt-1 text-sm text-slate-500">私有車輛管理</p>
      </div>

      {firstRun && (
        <div className="rounded-xl border border-brand-500/40 bg-brand-500/10 px-4 py-3 text-sm text-brand-300">
          這是全新安裝。第一個註冊的帳號會成為<b>最高權限管理員</b>。
        </div>
      )}
      {notice && effective === "login" && (
        <div role="status" className="rounded-xl bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">{notice}</div>
      )}

      {closed && (
        <div role="status" className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
          目前未開放註冊。若需要帳號，請洽管理員新增或開放註冊。
        </div>
      )}

      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); setNotice(null); m.mutate(); }}>
        <Field label="帳號" hint={effective === "register" ? "3–32 字，英數與 _ . -" : undefined}>
          <input className="input" autoComplete="username" autoCapitalize="none" value={username}
            onChange={(e) => setUsername(e.target.value)} required />
        </Field>
        <Field label="密碼" hint={effective === "register" ? "至少 8 碼" : undefined}>
          <input className="input" type="password" value={password} minLength={effective === "register" ? 8 : undefined}
            autoComplete={effective === "login" ? "current-password" : "new-password"}
            onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        {effective === "register" && (
          <Field label="確認密碼">
            <input className="input" type="password" autoComplete="new-password" value={confirm}
              onChange={(e) => setConfirm(e.target.value)} required />
          </Field>
        )}
        {effective === "register" && firstRun && reg.data?.needs_setup_token && (
          <Field label="初始設定碼" hint="伺服器環境變數 MOTOQ_SETUP_TOKEN">
            <input className="input" value={token} onChange={(e) => setToken(e.target.value)} required />
          </Field>
        )}
        <ErrorText error={m.error} />
        <button className="btn-primary w-full" disabled={m.isPending || closed}>
          {m.isPending ? "處理中…" : effective === "login" ? "登入" : firstRun ? "建立管理員帳號" : "註冊"}
        </button>
      </form>

      {!firstRun && (
        <div className="text-center text-sm text-slate-500">
          {effective === "login" ? (
            <button className="btn-ghost w-full" onClick={() => { setMode("register"); m.reset(); }}>
              註冊新帳號{reg.data?.mode === "approval" ? "（需管理員核准）" : ""}
            </button>
          ) : (
            <button className="gold-text underline" onClick={() => { setMode("login"); m.reset(); }}>
              已有帳號？登入
            </button>
          )}
        </div>
      )}
    </div>
  );
}
