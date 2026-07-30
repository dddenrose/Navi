import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { signOut } from "firebase/auth";
import {
  LayoutDashboard,
  MessageSquare,
  TrendingUp,
  Briefcase,
  ScanSearch,
  Lock,
  Menu,
  X,
  ChevronLeft,
  LogOut,
  Sun,
  Moon,
  type LucideIcon,
} from "lucide-react";
import { auth } from "@/lib/firebase";
import { useAllowedFeatures } from "@/lib/queries/account";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore } from "@/store/themeStore";
import { useTokenClaims } from "@/lib/useTokenClaims";
import NaviLogo from "@/components/NaviLogo";

const ICON_SIZE = 16;
const ICON_STROKE = 1.7;

const navItems: {
  to: string;
  label: string;
  featureKey?: string;
  icon: LucideIcon;
}[] = [
  { to: "/dashboard", label: "總覽", icon: LayoutDashboard },
  { to: "/chat", label: "對話", featureKey: "chat", icon: MessageSquare },
  { to: "/stock", label: "股票", featureKey: "stock", icon: TrendingUp },
  {
    to: "/portfolio",
    label: "投資組合",
    featureKey: "portfolio",
    icon: Briefcase,
  },
  {
    to: "/screener",
    label: "智能選股",
    featureKey: "screener",
    icon: ScanSearch,
  },
];

// nav active 態統一用 accent-soft + border-strong，admin 與一般項目不分色系
const activeNavStyle = {
  background: "var(--accent-soft)",
  border: "1px solid var(--border-strong)",
};

export default function Layout() {
  const { user } = useAuthStore();
  const { theme, toggleTheme } = useThemeStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  // 與 Dashboard、FeatureGuard 共用同一份權限快取（見 lib/queries/account.ts）
  const allowedFeatures = useAllowedFeatures();
  const claims = useTokenClaims();
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

  const isGuest = user?.isAnonymous ?? false;
  const initials = isGuest
    ? "訪"
    : (user?.displayName?.[0]?.toUpperCase() ??
      user?.email?.[0]?.toUpperCase() ??
      "U");

  const visibleNavItems = navItems.filter(
    (item) =>
      claims.admin ||
      !item.featureKey ||
      allowedFeatures === null ||
      allowedFeatures.has(item.featureKey),
  );

  return (
    <div className="flex min-h-screen bg-base text-ink">
      {/* Mobile top bar */}
      <div className="fixed top-0 left-0 right-0 z-40 flex items-center h-14 px-4 md:hidden bg-surface border-b border-line-subtle">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="w-9 h-9 rounded-lg flex items-center justify-center bg-[var(--surface-2)] text-ink-secondary hover:text-ink-strong transition-colors"
          aria-label="切換選單"
        >
          {sidebarOpen ? (
            <X size={ICON_SIZE} strokeWidth={ICON_STROKE} aria-hidden="true" />
          ) : (
            <Menu
              size={ICON_SIZE}
              strokeWidth={ICON_STROKE}
              aria-hidden="true"
            />
          )}
        </button>
        <div className="flex items-center gap-2 ml-3">
          <span className="w-6 h-6 rounded-lg flex items-center justify-center bg-[var(--surface-2)] border border-line-subtle">
            <NaviLogo size={16} />
          </span>
          <span className="text-sm font-bold text-ink-strong">Navi</span>
        </div>
      </div>

      {/* Overlay backdrop (mobile) */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-[var(--modal-overlay)] md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed md:sticky md:top-0 md:h-screen inset-y-0 left-0 z-50 flex flex-col shrink-0 transform transition-all duration-200 ease-out md:translate-x-0 bg-surface border-r border-line-subtle ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{ width: collapsed ? "68px" : "256px" }}
      >
        {/* Logo */}
        <div
          className={`pt-6 pb-5 border-b border-line-subtle ${collapsed ? "px-3" : "px-6"}`}
        >
          <div
            className={`flex items-center ${collapsed ? "justify-center" : "gap-3"}`}
          >
            <span className="w-9 h-9 rounded-field flex items-center justify-center flex-shrink-0 bg-[var(--surface-2)] border border-line shadow-[var(--shadow-card)]">
              <NaviLogo size={22} />
            </span>
            {!collapsed && (
              <div>
                <span className="text-sm font-bold text-ink-strong">
                  Navi
                </span>
                <p className="text-xs text-ink-faint leading-none mt-0.5">
                  AI 投資助理
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Nav items */}
        <nav
          className={`flex-1 overflow-y-auto ${collapsed ? "px-2" : "px-4"} py-6 space-y-2`}
        >
          {visibleNavItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              title={collapsed ? label : undefined}
              className={({ isActive }) =>
                `flex items-center ${collapsed ? "justify-center" : "gap-3"} ${collapsed ? "px-0 py-3" : "px-4 py-3"} rounded-xl text-sm font-medium transition-colors duration-150 ${
                  isActive
                    ? "text-ink-strong"
                    : "text-ink-muted hover:text-ink hover:bg-[var(--surface-2)]"
                }`
              }
              style={({ isActive }) => (isActive ? activeNavStyle : {})}
            >
              <Icon
                size={ICON_SIZE}
                strokeWidth={ICON_STROKE}
                aria-hidden="true"
              />
              {!collapsed && label}
            </NavLink>
          ))}
          {claims.admin && (
            <NavLink
              to="/admin"
              title={collapsed ? "後台" : undefined}
              className={({ isActive }) =>
                `flex items-center ${collapsed ? "justify-center" : "gap-3"} ${collapsed ? "px-0 py-3" : "px-4 py-3"} rounded-xl text-sm font-medium transition-colors duration-150 ${
                  isActive
                    ? "text-ink-strong"
                    : "text-ink-muted hover:text-ink hover:bg-[var(--surface-2)]"
                }`
              }
              style={({ isActive }) => (isActive ? activeNavStyle : {})}
            >
              <Lock size={ICON_SIZE} strokeWidth={ICON_STROKE} aria-hidden="true" />
              {!collapsed && "後台"}
            </NavLink>
          )}
        </nav>

        {/* Collapse toggle (desktop only) */}
        <div className="hidden md:flex px-3 pb-2">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className={`${collapsed ? "w-full justify-center" : "ml-auto"} flex items-center gap-2 px-2 py-2 text-xs text-ink-faint hover:text-ink rounded-lg transition-colors hover:bg-[var(--surface-2)]`}
            aria-label={collapsed ? "展開側邊欄" : "收合側邊欄"}
            title={collapsed ? "展開側邊欄" : "收合側邊欄"}
          >
            <ChevronLeft
              size={ICON_SIZE}
              strokeWidth={ICON_STROKE}
              className={`transition-transform duration-200 ${collapsed ? "rotate-180" : ""}`}
              aria-hidden="true"
            />
            {!collapsed && <span>收合</span>}
          </button>
        </div>

        {/* User info + sign out */}
        <div
          className={`${collapsed ? "px-2" : "px-4"} py-5 border-t border-line-subtle`}
        >
          {!collapsed ? (
            <div className="flex items-center gap-2.5 px-3 py-3 rounded-xl mb-2 bg-[var(--surface-1)]">
              {user?.photoURL ? (
                <img
                  src={user.photoURL}
                  width={28}
                  height={28}
                  className="w-7 h-7 rounded-full flex-shrink-0 ring-1 ring-white/10"
                  alt="avatar"
                />
              ) : (
                <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 bg-[var(--surface-3)] text-[var(--accent)]">
                  {initials}
                </div>
              )}
              <div className="min-w-0">
                <p className="text-xs font-medium text-ink truncate">
                  {isGuest ? "訪客" : (user?.displayName ?? "使用者")}
                </p>
                <p className="text-xs text-ink-faint truncate">
                  {isGuest ? "訪客模式・登入可保留資料" : user?.email}
                </p>
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
                <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold bg-[var(--surface-3)] text-[var(--accent)]">
                  {initials}
                </div>
              )}
            </div>
          )}
          <button
            onClick={handleSignOut}
            title={collapsed ? "登出" : undefined}
            className={`w-full flex items-center ${collapsed ? "justify-center" : "gap-2"} px-3 py-2.5 text-xs text-ink-faint hover:text-red-400 rounded-xl transition-colors hover:bg-red-400/5`}
          >
            <LogOut size={ICON_SIZE} strokeWidth={ICON_STROKE} aria-hidden="true" />
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
            className={`w-full flex items-center ${collapsed ? "justify-center" : "gap-2"} px-3 py-2.5 text-xs text-ink-faint hover:text-ink rounded-xl transition-colors hover:bg-[var(--surface-2)] mt-1`}
            aria-label={theme === "dark" ? "切換至淺色模式" : "切換至暗色模式"}
          >
            {theme === "dark" ? (
              <Sun size={ICON_SIZE} strokeWidth={ICON_STROKE} aria-hidden="true" />
            ) : (
              <Moon size={ICON_SIZE} strokeWidth={ICON_STROKE} aria-hidden="true" />
            )}
            {!collapsed && (theme === "dark" ? "淺色模式" : "暗色模式")}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main
        id="main-content"
        className="flex-1 overflow-auto pt-14 md:pt-0 bg-base"
      >
        <Outlet />
      </main>
    </div>
  );
}
