import { lazy, Suspense } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { useAuth } from "./core/auth";
import Shell from "./ui/shell";

const Bidding = lazy(() => import("./pages/Bidding"));
const AgentHub = lazy(() => import("./pages/AgentHub"));
const Settings = lazy(() => import("./pages/Settings"));
const BigScreen = lazy(() => import("./pages/BigScreen"));
const Login = lazy(() => import("./pages/Login"));

function RouteFallback() {
  return (
    <div className="route-fallback" aria-busy="true">
      <div className="skeleton" style={{ height: 38, width: "42%" }} />
      <div className="grid g6" style={{ marginTop: 22 }}>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skeleton" style={{ height: 96, opacity: 1 - i * 0.08 }} />
        ))}
      </div>
      <div className="skeleton" style={{ height: 300, marginTop: 16 }} />
    </div>
  );
}

function RequireAuth() {
  const { me, loading } = useAuth();
  if (loading) return <RouteFallback />;
  if (!me) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export default function App() {
  return (
    <>
      <div className="aurora" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div className="grain" aria-hidden="true" />

      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<RequireAuth />}>
            <Route path="/screen" element={<BigScreen />} />
            <Route element={<Shell />}>
              <Route index element={<Bidding />} />
              <Route path="agent" element={<AgentHub />} />
              <Route path="settings" element={<Settings />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </>
  );
}
