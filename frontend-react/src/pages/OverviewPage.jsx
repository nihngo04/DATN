import { ArrowRight, Database, FileImage, Layers, MapPinned } from "lucide-react";
import MapView from "../components/MapView.jsx";
import StatCard from "../components/StatCard.jsx";

function WorkflowStep({ icon: Icon, title, detail, active }) {
  return (
    <div className={`workflow-step ${active ? "active" : ""}`}>
      <div className="step-icon">
        <Icon size={18} />
      </div>
      <div>
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
    </div>
  );
}

export default function OverviewPage({
  settings,
  stats,
  points,
  boundary,
  districts,
  lsm,
  focusPoint,
  lastResult,
  overviewMapView,
  setOverviewMapView,
}) {
  return (
    <section className="page-grid overview-grid">
      <div className="page-header span-2">
        <div>
          <p className="eyebrow">Workflow chính</p>
          <h1>Từ phát hiện sạt lở đến cập nhật bản đồ nhạy cảm</h1>
        </div>
        {lastResult?.point ? (
          <div className={`result-pill ${lastResult.decision}`}>
            {lastResult.decision === "new" ? "Điểm mới đã vào CSDL" : "Kết quả trùng điểm cũ"}
          </div>
        ) : null}
      </div>

      <div className="panel workflow-panel">
        <WorkflowStep
          active={Boolean(lastResult)}
          detail="Upload ảnh/video hoặc chọn ảnh mẫu trong data/segment"
          icon={FileImage}
          title="1. Nhận dữ liệu"
        />
        <ArrowRight className="workflow-arrow" size={18} />
        <WorkflowStep
          active={Boolean(lastResult?.prediction)}
          detail="Resize ảnh 512x512, gọi SegFormer endpoint và overlay mask"
          icon={Layers}
          title="2. Phân đoạn"
        />
        <ArrowRight className="workflow-arrow" size={18} />
        <WorkflowStep
          active={lastResult?.decision === "new"}
          detail="Đối chiếu điểm cũ, thêm bản ghi mới nếu đủ điều kiện"
          icon={Database}
          title="3. CSDL kiểm kê"
        />
        <ArrowRight className="workflow-arrow" size={18} />
        <WorkflowStep
          active={Boolean(lastResult?.susceptibility_map || lsm?.overlay_url)}
          detail="Sử dụng LSM thật nếu có, hoặc tạo/cập nhật từ điểm mới"
          icon={MapPinned}
          title="4. Bản đồ nhạy cảm"
        />
      </div>

      <div className="stats-strip span-2">
        <StatCard detail="điểm trong SQLite" label="CSDL kiểm kê" value={stats?.inventory_total ?? 0} />
        <StatCard detail="được thêm sau phát hiện" label="Điểm AI mới" tone="danger" value={stats?.new_inventory_total ?? 0} />
        <StatCard detail="kết quả workflow" label="Lần phát hiện" value={stats?.detection_jobs_total ?? 0} />
        <StatCard
          detail="tổng diện tích ước tính"
          label="Diện tích"
          value={`${Number(stats?.area_total_m2 || 0).toLocaleString("vi-VN", { maximumFractionDigits: 0 })} m2`}
        />
      </div>

      <div className="panel map-panel span-2">
        <div className="panel-heading">
          <div>
            <h2>Bản đồ vệ tinh khu vực nghiên cứu</h2>
            <p>Hiển thị boundary, ranh giới huyện và các điểm sạt lở. Dùng nút “Xem vị trí” sau phát hiện để zoom tới điểm mới.</p>
          </div>
        </div>
        <MapView
          boundary={boundary}
          districts={districts}
          focusPoint={focusPoint}
          lsm={lsm}
          points={points}
          savedView={overviewMapView}
          settings={settings}
          showLsm={false}
          onViewChange={setOverviewMapView}
          height="calc(100vh - 360px)"
        />
      </div>
    </section>
  );
}
