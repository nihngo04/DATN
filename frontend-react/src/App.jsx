import { useCallback, useEffect, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import StatusBanner from "./components/StatusBanner.jsx";
import { loadDashboardData } from "./api/client.js";
import OverviewPage from "./pages/OverviewPage.jsx";
import SegmentationPage from "./pages/SegmentationPage.jsx";
import InventoryPage from "./pages/InventoryPage.jsx";
import SusceptibilityPage from "./pages/SusceptibilityPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";

const initialData = {
  settings: null,
  stats: null,
  points: [],
  boundary: null,
  districts: null,
  rasters: [],
  lsm: null,
  susceptibilityMaps: [],
  samples: [],
};

export default function App() {
  const [activePage, setActivePage] = useState("overview");
  const [data, setData] = useState(initialData);
  const [status, setStatus] = useState({ type: "loading", message: "Đang nạp dữ liệu WebGIS..." });
  const [focusPoint, setFocusPoint] = useState(null);
  const [lastResult, setLastResult] = useState(null);
  const [segmentationOutput, setSegmentationOutput] = useState({ result: null, mode: "" });
  const [overviewMapView, setOverviewMapView] = useState(null);

  const refreshData = useCallback(async (silent = false) => {
    if (!silent) setStatus({ type: "loading", message: "Đang đồng bộ dữ liệu từ backend..." });
    try {
      const nextData = await loadDashboardData();
      setData(nextData);
      if (!silent) setStatus({ type: "success", message: "Dữ liệu đã sẵn sàng." });
      return nextData;
    } catch (error) {
      setStatus({
        type: "error",
        message: `Không kết nối được backend: ${error.message}`,
      });
      throw error;
    }
  }, []);

  useEffect(() => {
    refreshData().catch(() => {});
  }, [refreshData]);

  const viewLocation = useCallback((point) => {
    setFocusPoint({ ...point, focusId: Date.now() });
    setActivePage("overview");
  }, []);

  const pageProps = {
    ...data,
    status,
    setStatus,
    refreshData,
    focusPoint,
    lastResult,
    setLastResult,
    segmentationOutput,
    setSegmentationOutput,
    overviewMapView,
    setOverviewMapView,
    onViewLocation: viewLocation,
    setSettings: (settings) => setData((value) => ({ ...value, settings })),
    setLsm: (lsm) => setData((value) => ({ ...value, lsm })),
    setSusceptibilityMaps: (susceptibilityMaps) => setData((value) => ({ ...value, susceptibilityMaps })),
  };

  return (
    <div className="app-shell">
      <Sidebar activePage={activePage} onChange={setActivePage} stats={data.stats} />
      <main className="main-area">
        <StatusBanner status={status} onClose={() => setStatus(null)} />
        {activePage === "overview" ? <OverviewPage {...pageProps} /> : null}
        {activePage === "segmentation" ? <SegmentationPage {...pageProps} /> : null}
        {activePage === "inventory" ? <InventoryPage {...pageProps} /> : null}
        {activePage === "susceptibility" ? <SusceptibilityPage {...pageProps} /> : null}
        {activePage === "settings" ? <SettingsPage {...pageProps} /> : null}
      </main>
    </div>
  );
}
