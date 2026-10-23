import { Link } from "react-router-dom";
import type { Me } from "../api";
import Icon from "../components/Icon";
import { PageTitle } from "../components/ui";

export default function More({ me }: { me: Me }) {
  const items = [
    { to: "/vehicles", icon: "car", title: "車輛", sub: "新增、編輯、儀表更換" },
    { to: "/compliance", icon: "shield", title: "稅費與到期", sub: "牌照稅、保險、驗車" },
    { to: "/service", icon: "wrench", title: "維修履歷", sub: "進廠記錄與 PDF 匯出" },
    { to: "/reports", icon: "chart", title: "報表", sub: "年度持有成本、兩車比較" },
    { to: "/settings", icon: "gear", title: "設定", sub: "主題、提醒、匯出入、密碼" },
    ...(me.role === "admin" ? [{ to: "/admin", icon: "users", title: "管理後台", sub: "使用者、登入紀錄、安全設定" }] : []),
  ];
  return (
    <div className="space-y-4">
      <PageTitle>更多</PageTitle>
      <p className="text-sm text-slate-500">
        {me.username}・{me.role === "admin" ? "管理員" : "一般使用者"}
      </p>
      <ul className="space-y-2">
        {items.map((it) => (
          <li key={it.to}>
            <Link to={it.to} className="card flex items-center gap-4">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-500/15 text-brand-700 dark:text-brand-400">
                <Icon name={it.icon} className="h-6 w-6" />
              </span>
              <span>
                <span className="block font-semibold">{it.title}</span>
                <span className="block text-xs text-slate-500">{it.sub}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
