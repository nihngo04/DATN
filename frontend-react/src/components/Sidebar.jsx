import {
  Activity,
  Database,
  Layers,
  Map,
  PanelLeft,
  Radar,
  Settings,
} from "lucide-react";

const items = [
  { id: "overview", label: "Tổng thể", icon: Activity },
  { id: "segmentation", label: "Phân đoạn sạt lở", icon: Radar },
  { id: "inventory", label: "CSDL sạt lở", icon: Database },
  { id: "susceptibility", label: "Bản đồ nhạy cảm", icon: Map },
  { id: "settings", label: "Setting", icon: Settings },
];

export default function Sidebar({ activePage, onChange, stats }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">
          <PanelLeft size={19} />
        </div>
        <div>
          <strong>WebGIS Sạt lở</strong>
          <span>Quảng Trị</span>
        </div>
      </div>

      <nav className="nav-list" aria-label="Chức năng chính">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <button
              className={`nav-item ${activePage === item.id ? "active" : ""}`}
              key={item.id}
              onClick={() => onChange(item.id)}
              type="button"
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="sidebar-summary">
        <div className="summary-title">
          <Layers size={16} />
          <span>Trạng thái dữ liệu</span>
        </div>
        <div className="summary-row">
          <span>Điểm kiểm kê</span>
          <strong>{stats?.inventory_total ?? 0}</strong>
        </div>
        <div className="summary-row">
          <span>Điểm AI mới</span>
          <strong>{stats?.new_inventory_total ?? 0}</strong>
        </div>
        <div className="summary-row">
          <span>Lần phát hiện</span>
          <strong>{stats?.detection_jobs_total ?? 0}</strong>
        </div>
      </div>
    </aside>
  );
}
