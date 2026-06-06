import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LoginGate } from "./components/LoginGate";
import { Sidebar } from "./components/Sidebar";
import { ContributorPage } from "./pages/ContributorPage";
import { MetricDetail } from "./pages/MetricDetail";
import { OrgOverview } from "./pages/OrgOverview";
import { TeamDetail } from "./pages/TeamDetail";

export default function App() {
  return (
    <LoginGate>
      <BrowserRouter>
        <div className="flex h-screen bg-page">
          <Sidebar appName="EPD" />
          <main className="flex-1 overflow-y-auto p-8">
            <Routes>
              <Route path="/" element={<OrgOverview />} />
              <Route path="/teams/*" element={<TeamDetail />} />
              <Route path="/metrics/:metricKey" element={<MetricDetail />} />
              <Route path="/contributors/:login" element={<ContributorPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </LoginGate>
  );
}
