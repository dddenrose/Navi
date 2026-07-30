import { useEffect, lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "@/lib/firebase";
import { useAuthStore } from "@/store/authStore";
import ErrorBoundary from "@/components/ErrorBoundary";
import FeatureGuard from "@/components/FeatureGuard";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";

const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Chat = lazy(() => import("@/pages/Chat"));
const Stock = lazy(() => import("@/pages/Stock"));
const Portfolio = lazy(() => import("@/pages/Portfolio"));
const Screener = lazy(() => import("@/pages/Screener"));
const AdminLayout = lazy(() => import("@/pages/admin/AdminLayout"));
const AdminDashboard = lazy(() => import("@/pages/admin/AdminDashboard"));
const AdminUsers = lazy(() => import("@/pages/admin/AdminUsers"));
const AdminUserDetail = lazy(() => import("@/pages/admin/AdminUserDetail"));
const AdminQuotaConfigs = lazy(() => import("@/pages/admin/AdminQuotaConfigs"));
const AdminFeatureAccess = lazy(
  () => import("@/pages/admin/AdminFeatureAccess"),
);
const AdminLogs = lazy(() => import("@/pages/admin/AdminLogs"));

function PageFallback() {
  return (
    <div className="flex items-center justify-center h-full min-h-[50vh]">
      <p className="text-sm text-ink-muted">載入中\u2026</p>
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
                  <FeatureGuard featureKey="stock" featureName="股票分析">
                    <ErrorBoundary>
                      <Stock />
                    </ErrorBoundary>
                  </FeatureGuard>
                }
              />
              <Route
                path="stock/:symbol"
                element={
                  <FeatureGuard featureKey="stock" featureName="股票分析">
                    <ErrorBoundary>
                      <Stock />
                    </ErrorBoundary>
                  </FeatureGuard>
                }
              />
              <Route
                path="portfolio"
                element={
                  <FeatureGuard featureKey="portfolio" featureName="投資組合">
                    <ErrorBoundary>
                      <Portfolio />
                    </ErrorBoundary>
                  </FeatureGuard>
                }
              />
              <Route
                path="screener"
                element={
                  <FeatureGuard featureKey="screener" featureName="智能選股">
                    <ErrorBoundary>
                      <Screener />
                    </ErrorBoundary>
                  </FeatureGuard>
                }
              />
              <Route
                path="admin"
                element={
                  <ErrorBoundary>
                    <AdminLayout />
                  </ErrorBoundary>
                }
              >
                <Route index element={<AdminDashboard />} />
                <Route path="users" element={<AdminUsers />} />
                <Route path="users/:uid" element={<AdminUserDetail />} />
                <Route path="quota" element={<AdminQuotaConfigs />} />
                <Route path="permissions" element={<AdminFeatureAccess />} />
                <Route path="logs" element={<AdminLogs />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
