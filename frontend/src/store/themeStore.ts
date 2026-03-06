import { create } from "zustand";

type Theme = "dark" | "light";

interface ThemeState {
  theme: Theme;
  toggleTheme: () => void;
}

function getInitialTheme(): Theme {
  try {
    const stored = localStorage.getItem("navi-theme");
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // localStorage unavailable
  }
  return "dark";
}

export const useThemeStore = create<ThemeState>((set) => ({
  theme: getInitialTheme(),
  toggleTheme: () =>
    set((state) => {
      const next = state.theme === "dark" ? "light" : "dark";
      try {
        localStorage.setItem("navi-theme", next);
      } catch {
        // ignore
      }
      document.documentElement.setAttribute("data-theme", next);
      return { theme: next };
    }),
}));

// Apply initial theme on module load
document.documentElement.setAttribute("data-theme", getInitialTheme());
