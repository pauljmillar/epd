import { Sidebar } from "./components/Sidebar";
import { OrgOverview } from "./pages/OrgOverview";

export default function App() {
  return (
    <div className="flex h-screen bg-page">
      <Sidebar appName="EPD" />
      <main className="flex-1 overflow-y-auto p-8">
        <OrgOverview />
      </main>
    </div>
  );
}
