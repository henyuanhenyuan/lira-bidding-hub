import { lazy, Suspense } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { useAuth } from "./core/auth";
import { Boundary } from "./ui/Boundary";
import Shell from "./ui/Shell";

const Control = lazy(() => import("./pages/Control"));
const Bidding = lazy(() => import("./pages/Bidding"));
const Agents = lazy(() => import("./pages/Agents"));
const Sources = lazy(() => import("./pages/Sources"));
const Evaluation = lazy(() => import("./pages/Evaluation"));
const Settings = lazy(() => import("./pages/Settings"));
const Screen = lazy(() => import("./pages/Screen"));
const Login = lazy(() => import("./pages/Login"));

function Fallback() {
  return (
    <div className="boot">
      <span className="boot-orb" />
      <p>正在接入竞价中枢…</p>
    </div>
  );
}

function RequireAuth() {
  const { me, loading } = useAuth();
  if (loading) return <Fallback />;
  if (!me) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export default function App() {
  return (
    <Suspense fallback={<Fallback />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth />}>
          <Route
            path="/screen"
            element={
              <Boundary>
                <Screen />
              </Boundary>
            }
          />
          <Route element={<Shell />}>
            <Route index element={<Control />} />
            <Route path="/bidding" element={<Bidding />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/sources" element={<Sources />} />
            <Route path="/evaluation" element={<Evaluation />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
