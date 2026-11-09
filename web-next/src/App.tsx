import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { api } from "./core/api";
import { useAuth } from "./core/auth";
import { Shell } from "./ui/kit";

const Workspace = lazy(() => import("./pages/Workspace"));
const Data = lazy(() => import("./pages/Data"));
const AgentHub = lazy(() => import("./pages/AgentHub"));
const BigScreen = lazy(() => import("./pages/BigScreen"));
const Knowledge = lazy(() => import("./pages/Knowledge"));
const Login = lazy(() => import("./pages/Login"));
const Settings = lazy(() => import("./pages/Settings"));

function Boot() {
  return <div className="loader">正在载入…</div>;
}

function RequireAuth() {
  const { me, loading } = useAuth();
  if (loading) return <Boot />;
  if (!me) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function Layout() {
  const [pending, setPending] = useState(0);
  useEffect(() => {
    let alive = true;
    const load = () => {
      if (document.hidden) return;
      void api
        .get<unknown[]>("/api/approvals/inbox")
        .then((rows) => alive && setPending(rows.length))
        .catch(() => undefined);
    };
    const onVisible = () => {
      if (!document.hidden) load();
    };
    load();
    const timer = window.setInterval(load, 30_000);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);
  return (
    <Shell pending={pending}>
      <Outlet />
    </Shell>
  );
}

export default function App() {
  return (
    <Suspense fallback={<Boot />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth />}>
          <Route path="screen" element={<BigScreen />} />
          <Route element={<Layout />}>
            <Route index element={<Workspace />} />
            <Route path="data" element={<Data />} />
            <Route path="agent" element={<AgentHub />} />
            <Route path="knowledge" element={<Knowledge />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Route>
      </Routes>
    </Suspense>
  );
}
