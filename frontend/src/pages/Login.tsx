import { useState } from "react";
import { Navigate } from "react-router-dom";
import { signInWithPopup, signInWithEmailAndPassword } from "firebase/auth";
import { auth, googleProvider } from "@/lib/firebase";
import { useAuthStore } from "@/store/authStore";

export default function Login() {
  const { user, loading } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleGoogleSignIn = async () => {
    setError("");
    setSubmitting(true);
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "登入失敗");
    } finally {
      setSubmitting(false);
    }
  };

  const handleEmailSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await signInWithEmailAndPassword(auth, email, password);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "登入失敗");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="relative min-h-screen flex items-center justify-center px-4 overflow-hidden"
      style={{
        background: "var(--login-bg)",
      }}
    >
      {/* Ambient orbs */}
      <div
        className="orb-1 absolute top-1/4 -left-32 w-80 h-80 rounded-full pointer-events-none"
        style={{
          background: `radial-gradient(circle, var(--login-orb1) 0%, transparent 70%)`,
        }}
      />
      <div
        className="orb-2 absolute bottom-1/4 -right-32 w-96 h-96 rounded-full pointer-events-none"
        style={{
          background: `radial-gradient(circle, var(--login-orb2) 0%, transparent 70%)`,
        }}
      />

      <div className="relative w-full max-w-sm animate-fade-up">
        {/* Logo */}
        <div className="text-center mb-8">
          <div
            className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-5"
            style={{
              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
              boxShadow: "0 0 32px rgba(99,102,241,0.4)",
            }}
          >
            <span className="text-3xl">🧭</span>
          </div>
          <h1
            className="text-2xl font-bold gradient-text"
            style={{ textWrap: "balance" }}
          >
            Navi
          </h1>
          <p className="text-slate-500 text-sm mt-2.5 tracking-wide">
            AI 投資分析助理
          </p>
        </div>

        {/* Card */}
        <div className="glass-md rounded-2xl p-8 shadow-2xl">
          <h2
            className="text-base font-semibold text-slate-200 mb-6"
            style={{ textWrap: "balance" }}
          >
            登入帳號
          </h2>

          {error && (
            <div
              role="alert"
              aria-live="polite"
              className="mb-4 px-4 py-3 rounded-xl text-sm text-red-300"
              style={{
                background: "rgba(239,68,68,0.08)",
                border: "1px solid rgba(239,68,68,0.2)",
              }}
            >
              {error}
            </div>
          )}

          {/* Email/Password */}
          <form onSubmit={handleEmailSignIn} className="space-y-4 mb-5">
            <div>
              <label htmlFor="login-email" className="sr-only">
                電子郵件
              </label>
              <input
                id="login-email"
                type="email"
                name="email"
                autoComplete="email"
                spellCheck={false}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="電子郵件（例：user@example.com）…"
                required
                className="input-field w-full rounded-xl px-4 py-3.5 text-sm text-slate-100 placeholder-slate-600 color-scheme-dark"
              />
            </div>
            <div>
              <label htmlFor="login-password" className="sr-only">
                密碼
              </label>
              <input
                id="login-password"
                type="password"
                name="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="密碼…"
                required
                className="input-field w-full rounded-xl px-4 py-3.5 text-sm text-slate-100 placeholder-slate-600"
              />
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-xl py-3.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
              style={{
                background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                boxShadow: submitting
                  ? "none"
                  : "0 4px 20px rgba(99,102,241,0.35)",
              }}
            >
              {submitting ? "登入中…" : "登入"}
            </button>
          </form>

          {/* Divider */}
          <div className="flex items-center gap-3 my-6">
            <div
              className="flex-1 h-px"
              style={{ background: "var(--divider)" }}
            />
            <span className="text-xs text-slate-600">或</span>
            <div
              className="flex-1 h-px"
              style={{ background: "var(--divider)" }}
            />
          </div>

          {/* Google */}
          <button
            onClick={handleGoogleSignIn}
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2.5 rounded-xl py-2.5 text-sm font-medium text-slate-200 transition-opacity hover:opacity-80 disabled:opacity-40"
            style={{
              background: "var(--overlay-subtle)",
              border: "1px solid var(--border-light)",
            }}
          >
            <svg viewBox="0 0 24 24" className="w-4 h-4" aria-hidden="true">
              <path
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                fill="#4285F4"
              />
              <path
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                fill="#34A853"
              />
              <path
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                fill="#FBBC05"
              />
              <path
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                fill="#EA4335"
              />
            </svg>
            Google 登入
          </button>
        </div>
      </div>
    </div>
  );
}
