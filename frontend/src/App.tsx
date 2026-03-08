import { useEffect, lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "@/lib/firebase";
import { useAuthStore } from "@/store/authStore";
import ErrorBoundary from "@/components/ErrorBoundary";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";

const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Chat = lazy(() => import("@/pages/Chat"));
const Stock = lazy(() => import("@/pages/Stock"));
const Portfolio = lazy(() => import("@/pages/Portfolio"));
const Backtest = lazy(() => import("@/pages/Backtest"));

function PageFallback() {
  return (
    <div className="flex items-center justify-center h-full min-h-[50vh]">
      <p className="text-sm text-slate-500">載入中\u2026</p>
    </div>
  );
}

export default function App() {
  const { setUser, setLoading } = useAuthStore();

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setUser(user);
      setLoading(false);
    });
    return unsubscribe;
  }, [setUser, setLoading]);

  return (
    <BrowserRouter>
      <ErrorBoundary>
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route
                path="dashboard"
                element={
                  <ErrorBoundary>
                    <Dashboard />
                  </ErrorBoundary>
                }
              />
              <Route
                path="chat"
                element={
                  <ErrorBoundary>
                    <Chat />
                  </ErrorBoundary>
                }
              />
              <Route
                path="chat/:conversationId"
                element={
                  <ErrorBoundary>
                    <Chat />
                  </ErrorBoundary>
                }
              />
              <Route
                path="stock"
                element={
                  <ErrorBoundary>
                    <Stock />
                  </ErrorBoundary>
                }
              />
              <Route
                path="stock/:symbol"
                element={
                  <ErrorBoundary>
                    <Stock />
                  </ErrorBoundary>
                }
              />
              <Route
                path="portfolio"
                element={
                  <ErrorBoundary>
                    <Portfolio />
                  </ErrorBoundary>
                }
              />
              <Route
                path="backtest"
                element={
                  <ErrorBoundary>
                    <Backtest />
                  </ErrorBoundary>
                }
              />
            </Route>
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
