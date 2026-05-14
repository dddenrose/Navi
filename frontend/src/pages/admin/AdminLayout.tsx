import { NavLink, Outlet, Navigate, useLocation } from "react-router-dom";
import { useTokenClaims } from "@/lib/useTokenClaims";

const items = [
  { to: "/admin", label: "總覽", end: true },
  { to: "/admin/users", label: "使用者" },
  { to: "/admin/quota", label: "額度設定" },
  { to: "/admin/permissions", label: "功能權限" },
  { to: "/admin/logs", label: "Audit Log" },
];

export default function AdminLayout() {
  const claims = useTokenClaims();
  const location = useLocation();

  if (!claims.loaded) {
    return (
      <div className="flex items-center justify-center h-full min-h-[40vh]">
        <p className="text-sm text-slate-500">載入中…</p>
      </div>
    );
  }
  if (!claims.admin) {
    return <Navigate to="/dashboard" replace state={{ from: location }} />;
  }

  return (
    <div className="flex flex-col h-full">
      <div
        className="px-6 py-4 flex items-center gap-6 flex-shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div>
          <h1 className="text-lg font-bold gradient-text">Navi 後台</h1>
          <p className="text-[11px] text-slate-600">使用者額度與權限管理</p>
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
                    ? "text-white"
                    : "text-slate-500 hover:text-slate-200 hover:bg-white/5"
                }`
              }
              style={({ isActive }) =>
                isActive
                  ? {
                      background:
                        "linear-gradient(135deg, rgba(99,102,241,0.25), rgba(139,92,246,0.15))",
                      border: "1px solid rgba(99,102,241,0.3)",
                    }
                  : {}
              }
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
