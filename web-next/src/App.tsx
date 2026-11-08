import { useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { api } from "./core/api";
import { useAuth } from "./core/auth";
import { Shell } from "./ui/kit";

import AgentHub from "./pages/AgentHub";
import BigScreen from "./pages/BigScreen";
import Knowledge from "./pages/Knowledge";
import Login from "./pages/Login";
import Settings from "./pages/Settings";
import Workspace from "./pages/Workspace";

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
    const load = () =>
      api
        .get<unknown[]>("/api/approvals/inbox")
        .then((rows) => alive && setPending(rows.length))
        .catch(() => undefined);
    void load();
    const timer = window.setInterval(load, 30_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
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
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth />}>
        <Route path="screen" element={<BigScreen />} />
        <Route element={<Layout />}>
          <Route index element={<Workspace />} />
          <Route path="agent" element={<AgentHub />} />
          <Route path="knowledge" element={<Knowledge />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
