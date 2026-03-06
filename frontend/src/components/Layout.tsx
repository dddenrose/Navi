import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { signOut } from "firebase/auth";
import { auth } from "@/lib/firebase";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore } from "@/store/themeStore";

const navItems = [
  {
    to: "/dashboard",
    label: "總覽",
    icon: (
      <svg
        viewBox="0 0 20 20"
        fill="currentColor"
        className="w-4 h-4"
        aria-hidden="true"
      >
        <path d="M2 10a8 8 0 018-8v8h8a8 8 0 11-16 0z" />
        <path d="M12 2.252A8.014 8.014 0 0117.748 8H12V2.252z" />
      </svg>
    ),
  },
  {
    to: "/chat",
    label: "對話",
    icon: (
      <svg
        viewBox="0 0 20 20"
        fill="currentColor"
        className="w-4 h-4"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z"
          clipRule="evenodd"
        />
      </svg>
    ),
  },
  {
    to: "/stock",
    label: "股票",
    icon: (
      <svg
        viewBox="0 0 20 20"
        fill="currentColor"
        className="w-4 h-4"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M3 3a1 1 0 000 2v8a2 2 0 002 2h2.586l-1.293 1.293a1 1 0 101.414 1.414L10 15.414l2.293 2.293a1 1 0 001.414-1.414L12.414 15H15a2 2 0 002-2V5a1 1 0 100-2H3zm11 4a1 1 0 10-2 0v4a1 1 0 102 0V7zm-3 1a1 1 0 10-2 0v3a1 1 0 102 0V8zM8 9a1 1 0 00-2 0v2a1 1 0 102 0V9z"
          clipRule="evenodd"
        />
      </svg>
    ),
  },
  {
    to: "/portfolio",
    label: "投資組合",
    icon: (
      <svg
        viewBox="0 0 20 20"
        fill="currentColor"
        className="w-4 h-4"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M6 6V5a3 3 0 013-3h2a3 3 0 013 3v1h2a2 2 0 012 2v3.57A22.952 22.952 0 0110 13a22.95 22.95 0 01-8-1.43V8a2 2 0 012-2h2zm2-1a1 1 0 011-1h2a1 1 0 011 1v1H8V5zm1 5a1 1 0 011-1h.01a1 1 0 110 2H10a1 1 0 01-1-1z"
          clipRule="evenodd"
        />
        <path d="M2 13.692V16a2 2 0 002 2h12a2 2 0 002-2v-2.308A24.974 24.974 0 0110 15c-2.796 0-5.487-.46-8-1.308z" />
      </svg>
    ),
  },
  {
    to: "/backtest",
    label: "策略回測",
    icon: (
      <svg
        viewBox="0 0 20 20"
        fill="currentColor"
        className="w-4 h-4"
        aria-hidden="true"
      >
        <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zm6-4a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zm6-3a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
      </svg>
    ),
  },
];

export default function Layout() {
  const { user } = useAuthStore();
  const { theme, toggleTheme } = useThemeStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();

  // Close sidebar on route change (mobile)
  const [prevPathname, setPrevPathname] = useState(location.pathname);
  if (location.pathname !== prevPathname) {
    setPrevPathname(location.pathname);
    setSidebarOpen(false);
  }

  const handleSignOut = async () => {
    await signOut(auth);
  };

  const initials =
    user?.displayName?.[0]?.toUpperCase() ??
    user?.email?.[0]?.toUpperCase() ??
    "U";

  return (
    <div
      className="flex min-h-screen"
      style={{ background: "var(--bg-base)", color: "var(--text-primary)" }}
    >
      {/* Mobile top bar */}
      <div
        className="fixed top-0 left-0 right-0 z-40 flex items-center h-14 px-4 md:hidden"
        style={{
          background: "var(--bg-surface)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="w-9 h-9 rounded-lg flex items-center justify-center text-slate-400 hover:text-white transition-colors"
          style={{ background: "var(--card-bg-hover)" }}
          aria-label="切換選單"
        >
          {sidebarOpen ? (
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className="w-5 h-5"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          ) : (
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className="w-5 h-5"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z"
                clipRule="evenodd"
              />
            </svg>
          )}
        </button>
        <div className="flex items-center gap-2 ml-3">
          <div
            className="w-6 h-6 rounded-md flex items-center justify-center text-xs"
            style={{
              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
            }}
          >
            🧭
          </div>
          <span className="text-sm font-bold gradient-text">Navi</span>
        </div>
      </div>

      {/* Overlay backdrop (mobile) */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed md:static inset-y-0 left-0 z-50 flex flex-col flex-shrink-0 transform transition-all duration-200 ease-out md:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{
          width: collapsed ? "68px" : "256px",
          background: "var(--bg-surface)",
          borderRight: "1px solid var(--border)",
        }}
      >
        {/* Logo */}
        <div
          className={`pt-6 pb-5 ${collapsed ? "px-3" : "px-6"}`}
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div
            className={`flex items-center ${collapsed ? "justify-center" : "gap-3"}`}
          >
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center text-base flex-shrink-0"
              style={{
                background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                boxShadow: "0 0 16px rgba(99,102,241,0.3)",
              }}
            >
              🧭
            </div>
            {!collapsed && (
              <div>
                <span className="text-sm font-bold gradient-text">Navi</span>
                <p className="text-xs text-slate-600 leading-none mt-0.5">
                  AI 投資助理
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Nav items */}
        <nav className={`flex-1 ${collapsed ? "px-2" : "px-4"} py-6 space-y-2`}>
          {navItems.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              title={collapsed ? label : undefined}
              className={({ isActive }) =>
                `flex items-center ${collapsed ? "justify-center" : "gap-3"} ${collapsed ? "px-0 py-3" : "px-4 py-3"} rounded-xl text-sm font-medium transition-colors duration-150 ${
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
              {icon}
              {!collapsed && label}
            </NavLink>
          ))}
        </nav>

        {/* Collapse toggle (desktop only) */}
        <div className="hidden md:flex px-3 pb-2">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className={`${collapsed ? "w-full justify-center" : "ml-auto"} flex items-center gap-2 px-2 py-2 text-xs text-slate-600 hover:text-slate-200 rounded-lg transition-colors hover:bg-white/5`}
            aria-label={collapsed ? "展開側邊欄" : "收合側邊欄"}
            title={collapsed ? "展開側邊欄" : "收合側邊欄"}
          >
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className={`w-4 h-4 transition-transform duration-200 ${collapsed ? "rotate-180" : ""}`}
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z"
                clipRule="evenodd"
              />
            </svg>
            {!collapsed && <span>收合</span>}
          </button>
        </div>

        {/* User info + sign out */}
        <div
          className={`${collapsed ? "px-2" : "px-4"} py-5`}
          style={{ borderTop: "1px solid var(--border)" }}
        >
          {!collapsed ? (
            <div
              className="flex items-center gap-2.5 px-3 py-3 rounded-xl mb-2"
              style={{ background: "var(--card-bg)" }}
            >
              {user?.photoURL ? (
                <img
                  src={user.photoURL}
                  width={28}
                  height={28}
                  className="w-7 h-7 rounded-full flex-shrink-0 ring-1 ring-white/10"
                  alt="avatar"
                />
              ) : (
                <div
                  className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                  style={{
                    background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                  }}
                >
                  {initials}
                </div>
              )}
              <div className="min-w-0">
                <p className="text-xs font-medium text-slate-300 truncate">
                  {user?.displayName ?? "使用者"}
                </p>
                <p className="text-xs text-slate-600 truncate">{user?.email}</p>
              </div>
            </div>
          ) : (
            <div className="flex justify-center mb-2">
              {user?.photoURL ? (
                <img
                  src={user.photoURL}
                  width={28}
                  height={28}
                  className="w-7 h-7 rounded-full ring-1 ring-white/10"
                  alt="avatar"
                />
              ) : (
                <div
                  className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                  style={{
                    background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                  }}
                >
                  {initials}
                </div>
              )}
            </div>
          )}
          <button
            onClick={handleSignOut}
            title={collapsed ? "登出" : undefined}
            className={`w-full flex items-center ${collapsed ? "justify-center" : "gap-2"} px-3 py-2.5 text-xs text-slate-600 hover:text-red-400 rounded-xl transition-colors hover:bg-red-400/5`}
          >
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className="w-3.5 h-3.5"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M3 3a1 1 0 00-1 1v12a1 1 0 102 0V4a1 1 0 00-1-1zm10.293 9.293a1 1 0 001.414 1.414l3-3a1 1 0 000-1.414l-3-3a1 1 0 10-1.414 1.414L14.586 9H7a1 1 0 100 2h7.586l-1.293 1.293z"
                clipRule="evenodd"
              />
            </svg>
            {!collapsed && "登出"}
          </button>
          <button
            onClick={toggleTheme}
            title={
              collapsed
                ? theme === "dark"
                  ? "淺色模式"
                  : "暗色模式"
                : undefined
            }
            className={`w-full flex items-center ${collapsed ? "justify-center" : "gap-2"} px-3 py-2.5 text-xs text-slate-600 hover:text-slate-200 rounded-xl transition-colors hover:bg-white/5 mt-1`}
            aria-label={theme === "dark" ? "切換至淺色模式" : "切換至暗色模式"}
          >
            {theme === "dark" ? (
              <svg
                viewBox="0 0 20 20"
                fill="currentColor"
                className="w-3.5 h-3.5"
                aria-hidden="true"
              >
                <path
                  fillRule="evenodd"
                  d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z"
                  clipRule="evenodd"
                />
              </svg>
            ) : (
              <svg
                viewBox="0 0 20 20"
                fill="currentColor"
                className="w-3.5 h-3.5"
                aria-hidden="true"
              >
                <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
              </svg>
            )}
            {!collapsed && (theme === "dark" ? "淺色模式" : "暗色模式")}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main
        id="main-content"
        className="flex-1 overflow-auto pt-14 md:pt-0"
        style={{ background: "var(--bg-base)" }}
      >
        <Outlet />
      </main>
    </div>
  );
}
