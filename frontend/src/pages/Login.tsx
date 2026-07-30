import { useState } from "react";
import { Navigate } from "react-router-dom";
import {
  signInWithPopup,
  signInWithEmailAndPassword,
  signInAnonymously,
} from "firebase/auth";
import { Eye } from "lucide-react";
import { auth, googleProvider } from "@/lib/firebase";
import { useAuthStore } from "@/store/authStore";
import NaviLogo from "@/components/NaviLogo";
import ParticleField from "@/components/ParticleField";

/** Firebase 錯誤碼 → 中文可行動訊息（原始英文錯誤碼對散戶不可讀） */
function authErrorMessage(e: unknown): string {
  const code =
    typeof e === "object" && e !== null && "code" in e
      ? String((e as { code: unknown }).code)
      : "";
  switch (code) {
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
      return "帳號或密碼錯誤，請重新輸入";
    case "auth/invalid-email":
      return "電子郵件格式不正確";
    case "auth/too-many-requests":
      return "嘗試次數過多，請稍後再試";
    case "auth/user-disabled":
      return "此帳號已被停用，請聯繫管理員";
    case "auth/popup-closed-by-user":
    case "auth/cancelled-popup-request":
      return "登入視窗已關閉，請再試一次";
    case "auth/network-request-failed":
      return "網路連線異常，請檢查網路後重試";
    case "auth/admin-restricted-operation":
    case "auth/operation-not-allowed":
      return "訪客模式暫時無法使用，請改用其他方式登入";
    default:
      return "登入失敗，請稍後再試";
  }
}

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
      setError(authErrorMessage(e));
    } finally {
      setSubmitting(false);
    }
  };

  const handleGuestSignIn = async () => {
    setError("");
    setSubmitting(true);
    try {
      await signInAnonymously(auth);
    } catch (e: unknown) {
      setError(authErrorMessage(e));
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
      setError(authErrorMessage(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative min-h-screen flex items-center justify-center px-4 overflow-hidden bg-base">
      {/* 靜態低 alpha 的 radial accent 底，不動畫，與粒子背景疊加出層次 */}
      <div
        aria-hidden="true"
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(circle at 30% 20%, var(--accent-soft), transparent 60%)",
        }}
      />
      <ParticleField interactive className="absolute inset-0" />

      <div className="relative w-full max-w-sm animate-fade-up">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-5 bg-[var(--surface-2)] border border-[var(--border-default)]">
            <NaviLogo size={32} />
          </div>
          <h1
            className="text-2xl font-bold text-ink-strong"
            style={{ textWrap: "balance" }}
          >
            Navi
          </h1>
          <p className="text-ink-muted text-sm mt-2.5 tracking-wide">
            AI 投資分析助理
          </p>
        </div>

        {/* Card */}
        <div
          className="relative glass-md rounded-2xl p-8 overflow-hidden"
          style={{ boxShadow: "var(--shadow-pop)" }}
        >
          {/* Signature hairline — 全站 signature 漸層限定 3 處之一 */}
          <div
            aria-hidden="true"
            className="absolute top-0 left-0 right-0 h-[2px]"
            style={{ background: "var(--gradient-signature)" }}
          />

          <h2
            className="text-base font-semibold text-ink mb-6"
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
                className="input-field rounded-xl px-4 py-3.5 text-sm"
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
                className="input-field rounded-xl px-4 py-3.5 text-sm"
              />
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="btn btn-primary w-full justify-center rounded-xl py-3.5 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitting ? "登入中…" : "登入"}
            </button>
          </form>

          {/* Divider */}
          <div className="flex items-center gap-3 my-6">
            <div className="flex-1 h-px bg-line-subtle" />
            <span className="text-xs text-ink-faint">或</span>
            <div className="flex-1 h-px bg-line-subtle" />
          </div>

          {/* Google */}
          <button
            onClick={handleGoogleSignIn}
            disabled={submitting}
            className="btn btn-ghost w-full justify-center rounded-xl py-2.5 text-sm disabled:opacity-40"
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

          {/* Guest */}
          <button
            onClick={handleGuestSignIn}
            disabled={submitting}
            className="btn btn-ghost w-full justify-center rounded-xl py-2.5 mt-3 text-sm disabled:opacity-40"
            style={{ borderStyle: "dashed" }}
          >
            <Eye className="w-4 h-4" aria-hidden="true" />
            以訪客身分體驗（免註冊）
          </button>
          <p className="text-[11px] text-ink-faint text-center mt-2.5">
            每日 10 則 AI 對話・訪客資料不長期保留
          </p>
        </div>
      </div>
    </div>
  );
}
