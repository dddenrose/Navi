import { NavLink, Outlet, Navigate, useLocation } from "react-router-dom";
import { useTokenClaims } from "@/lib/useTokenClaims";

const items = [
  { to: "/admin", label: "總覽", end: true },
  { to: "/admin/users", label: "使用者" },
  { to: "/admin/quota", label: "額度設定" },
  { to: "/admin/permissions", label: "功能權限" },
  { to: "/admin/logs", label: "Audit Log" },
];

// nav active 態統一用 accent-soft + border-strong，與 Layout.tsx 側欄一致
const activeNavStyle = {
  background: "var(--accent-soft)",
  border: "1px solid var(--border-strong)",
};

export default function AdminLayout() {
  const claims = useTokenClaims();
  const location = useLocation();

  if (!claims.loaded) {
    return (
      <div className="flex items-center justify-center h-full min-h-[40vh]">
        <p className="text-sm text-ink-muted">載入中…</p>
      </div>
    );
  }
  if (!claims.admin) {
    return <Navigate to="/dashboard" replace state={{ from: location }} />;
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 flex items-center gap-6 flex-shrink-0 border-b border-line-subtle">
        <div>
          <h1 className="text-lg font-bold text-ink-strong">Navi 後台</h1>
          <p className="text-[11px] text-ink-faint">使用者額度與權限管理</p>
        </div>
        <nav className="flex items-center gap-1 ml-auto">
          {items.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              end={it.end}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  isActive
                    ? "text-ink-strong"
                    : "text-ink-muted hover:text-ink hover:bg-[var(--surface-2)]"
                }`
              }
              style={({ isActive }) => (isActive ? activeNavStyle : {})}
            >
              {it.label}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <Outlet />
      </div>
    </div>
  );
}
