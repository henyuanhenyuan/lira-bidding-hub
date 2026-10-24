import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth";
import Layout from "./components/Layout";
import Admin from "./pages/Admin";
import AgentRuns from "./pages/AgentRuns";
import AgentTrace from "./pages/AgentTrace";
import Approvals from "./pages/Approvals";
import Ask from "./pages/Ask";
import Cases from "./pages/Cases";
import Collection from "./pages/Collection";
import CompetitorDetail from "./pages/CompetitorDetail";
import Competitors from "./pages/Competitors";
import Docs from "./pages/Docs";
import EvalPage from "./pages/EvalPage";
import EventDetail from "./pages/EventDetail";
import Events from "./pages/Events";
import ImportPage from "./pages/ImportPage";
import Skills from "./pages/Skills";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import Outcomes from "./pages/Outcomes";
import Overview from "./pages/Overview";
import SuggestionDetail from "./pages/SuggestionDetail";
import Suggestions from "./pages/Suggestions";

function RequireAuth() {
  const { me, loading } = useAuth();
  if (loading) {
    return (
      <div className="boot-screen">
        <div className="boot-mark">竞</div>
        <span>正在载入工作台…</span>
      </div>
    );
  }
  if (!me) return <Navigate to="/login" replace />;
  return <Outlet />;
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
          <Route path="competitors" element={<Competitors />} />
          <Route path="competitors/:id" element={<CompetitorDetail />} />
          <Route path="suggestions" element={<Suggestions />} />
          <Route path="suggestions/:id" element={<SuggestionDetail />} />
          <Route path="approvals" element={<Approvals />} />
          <Route path="outcomes" element={<Outcomes />} />
          <Route path="cases" element={<Cases />} />
          <Route path="docs" element={<Docs />} />
          <Route path="ask" element={<Ask />} />
          <Route path="agent" element={<AgentRuns />} />
          <Route path="agent/:id" element={<AgentTrace />} />
          <Route path="skills" element={<Skills />} />
          <Route path="eval" element={<EvalPage />} />
          <Route path="collection" element={<Collection />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="admin" element={<Admin />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  );
}
