import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LoginGate } from "./components/LoginGate";
import { Sidebar } from "./components/Sidebar";
import { ContributorPage } from "./pages/ContributorPage";
import { ContributorsIndex } from "./pages/ContributorsIndex";
import { MetricDetail } from "./pages/MetricDetail";
import { OrgOverview } from "./pages/OrgOverview";
import { RepoDetail } from "./pages/RepoDetail";
import { ReposIndex } from "./pages/ReposIndex";
import { SourcesIndex } from "./pages/SourcesIndex";
import { TeamDetail } from "./pages/TeamDetail";
import { TeamsIndex } from "./pages/TeamsIndex";

export default function App() {
  return (
    <LoginGate>
      <BrowserRouter>
        <div className="flex h-screen bg-page">
          <Sidebar appName="EPD" />
          <main className="flex-1 overflow-y-auto p-8">
            <Routes>
              <Route path="/" element={<OrgOverview />} />
              <Route path="/repos" element={<ReposIndex />} />
              <Route path="/repos/*" element={<RepoDetail />} />
              <Route path="/teams" element={<TeamsIndex />} />
              <Route path="/teams/:teamId/view" element={<TeamDetail />} />
              <Route path="/contributors" element={<ContributorsIndex />} />
              <Route path="/contributors/:login" element={<ContributorPage />} />
              <Route path="/sources" element={<SourcesIndex />} />
              <Route path="/metrics/:metricKey" element={<MetricDetail />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </LoginGate>
  );
}
