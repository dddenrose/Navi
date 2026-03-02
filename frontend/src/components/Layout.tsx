import { NavLink, Outlet } from "react-router-dom";
import { signOut } from "firebase/auth";
import { auth } from "@/lib/firebase";
import { useAuthStore } from "@/store/authStore";

const navItems = [
  { to: "/dashboard", label: "總覽", icon: "📊" },
  { to: "/chat", label: "對話", icon: "💬" },
  { to: "/stock", label: "股票", icon: "📈" },
];

export default function Layout() {
  const { user } = useAuthStore();

  const handleSignOut = async () => {
    await signOut(auth);
  };

  return (
    <div className="flex min-h-screen bg-slate-900 text-slate-100">
      {/* Sidebar */}
      <aside className="w-56 bg-slate-800 border-r border-slate-700 flex flex-col">
        {/* Logo */}
        <div className="px-5 py-4 border-b border-slate-700">
          <span className="text-xl font-bold text-indigo-400">🧭 Navi</span>
          <p className="text-xs text-slate-500 mt-0.5">AI 投資分析助理</p>
        </div>

        {/* Nav items */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? "bg-indigo-600 text-white"
                    : "text-slate-400 hover:bg-slate-700 hover:text-slate-100"
                }`
              }
            >
              <span>{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        {/* User info + sign out */}
        <div className="px-3 py-4 border-t border-slate-700">
          <div className="flex items-center gap-2 px-3 py-2 mb-2">
            {user?.photoURL ? (
              <img
                src={user.photoURL}
                className="w-7 h-7 rounded-full"
                alt="avatar"
              />
            ) : (
              <div className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center text-xs font-bold">
                {user?.displayName?.[0] ?? user?.email?.[0] ?? "U"}
              </div>
            )}
            <div className="min-w-0">
              <p className="text-xs font-medium text-slate-200 truncate">
                {user?.displayName ?? "使用者"}
              </p>
              <p className="text-xs text-slate-500 truncate">{user?.email}</p>
            </div>
          </div>
          <button
            onClick={handleSignOut}
            className="w-full text-left px-3 py-1.5 text-xs text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded-lg transition-colors"
          >
            登出
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
