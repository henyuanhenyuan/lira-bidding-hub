import { useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { api } from "./core/api";
import { useAuth } from "./core/auth";
import { Shell } from "./ui/kit";

import Approvals from "./pages/Approvals";
import Eval from "./pages/Eval";
import EventDetail from "./pages/EventDetail";
import Events from "./pages/Events";
import Knowledge from "./pages/Knowledge";
import Login from "./pages/Login";
import Observability from "./pages/Observability";
import Overview from "./pages/Overview";
import RunDetail from "./pages/RunDetail";
import Runs from "./pages/Runs";
import Settings from "./pages/Settings";
import SuggestionDetail from "./pages/SuggestionDetail";
import Suggestions from "./pages/Suggestions";
import Targets from "./pages/Targets";
import Tools from "./pages/Tools";

function Boot() {
  return <div className="loader">正在载入工作台…</div>;
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
    api
      .get<unknown[]>("/api/approvals/inbox")
      .then((rows) => alive && setPending(rows.length))
      .catch(() => undefined);
    return () => {
      alive = false;
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
        <Route element={<Layout />}>
          <Route index element={<Overview />} />
          <Route path="events" element={<Events />} />
          <Route path="events/:id" element={<EventDetail />} />
          <Route path="suggestions" element={<Suggestions />} />
          <Route path="suggestions/:id" element={<SuggestionDetail />} />
          <Route path="approvals" element={<Approvals />} />
          <Route path="runs" element={<Runs />} />
          <Route path="runs/:id" element={<RunDetail />} />
          <Route path="knowledge" element={<Knowledge />} />
          <Route path="tools" element={<Tools />} />
          <Route path="eval" element={<Eval />} />
          <Route path="observability" element={<Observability />} />
          <Route path="targets" element={<Targets />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
