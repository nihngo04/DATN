import { useMemo, useState } from "react";
import { Download, Search } from "lucide-react";
import { createReport, mediaUrl } from "../api/client.js";
import StatCard from "../components/StatCard.jsx";

function normalize(value) {
  return String(value || "").toLowerCase().trim();
}

export default function InventoryPage({ points, stats, setStatus, refreshData }) {
  const [query, setQuery] = useState("");
  const [district, setDistrict] = useState("");
  const [scale, setScale] = useState("");

  const districts = useMemo(
    () => [...new Set(points.map((point) => point.huyen).filter(Boolean))].sort(),
    [points],
  );
  const scales = useMemo(
    () => [...new Set(points.map((point) => point.quy_mo || "khong_ro"))].sort(),
    [points],
  );

  const filteredPoints = useMemo(() => {
    const q = normalize(query);
    return points.filter((point) => {
      const matchDistrict = !district || point.huyen === district;
      const pointScale = point.quy_mo || "khong_ro";
      const matchScale = !scale || pointScale === scale;
      const haystack = normalize(`${point.huyen} ${point.xa} ${point.thon} ${point.mo_ta} ${point.source}`);
      return matchDistrict && matchScale && (!q || haystack.includes(q));
    });
  }, [district, points, query, scale]);

  async function exportReport() {
    try {
      setStatus({ type: "loading", message: "Đang tạo báo cáo thống kê..." });
      const report = await createReport();
      await refreshData(true);
      setStatus({ type: "success", message: "Đã tạo báo cáo trong data/reports." });
      if (report.report_url) window.open(mediaUrl(report.report_url), "_blank", "noopener,noreferrer");
    } catch (error) {
      setStatus({ type: "error", message: error.message });
    }
  }

  return (
    <section className="page-grid inventory-grid">
      <div className="page-header span-2">
        <div>
          <p className="eyebrow">SQLite inventory</p>
          <h1>Cơ sở dữ liệu kiểm kê sạt lở</h1>
        </div>
        <button className="primary-button" onClick={exportReport} type="button">
          <Download size={17} />
          Tạo report
        </button>
      </div>

      <div className="stats-strip compact span-2">
        <StatCard label="Tổng điểm" value={stats?.inventory_total ?? 0} />
        <StatCard label="Điểm mới AI" tone="danger" value={stats?.new_inventory_total ?? 0} />
        <StatCard label="Kết quả trùng" value={stats?.duplicate_detection_jobs ?? 0} />
        <StatCard
          label="Diện tích kiểm kê"
          value={`${Number(stats?.area_total_m2 || 0).toLocaleString("vi-VN", { maximumFractionDigits: 0 })} m2`}
        />
      </div>

      <div className="panel inventory-stat-panel compact">
        <div className="panel-heading">
          <div>
            <h2>Thống kê theo huyện</h2>
            <p>Phân bố điểm sạt lở trong vùng nghiên cứu.</p>
          </div>
        </div>
        <div className="bar-list">
          {(stats?.by_huyen || []).map((item) => (
            <div className="bar-row" key={item.huyen || "unknown"}>
              <span>{item.huyen || "Không rõ"}</span>
              <div>
                <i style={{ width: `${Math.max(8, (item.total / Math.max(stats?.inventory_total || 1, 1)) * 100)}%` }} />
              </div>
              <strong>{item.total}</strong>
            </div>
          ))}
        </div>
      </div>

      <div className="panel inventory-stat-panel compact">
        <div className="panel-heading">
          <div>
            <h2>Thống kê theo quy mô</h2>
            <p>Tổng hợp nhanh để ưu tiên kiểm chứng.</p>
          </div>
        </div>
        <div className="scale-list">
          {(stats?.by_quy_mo || []).map((item) => (
            <div key={item.quy_mo || "unknown"}>
              <span>{item.quy_mo || "Không rõ"}</span>
              <strong>{item.total}</strong>
            </div>
          ))}
        </div>
      </div>

      <div className="panel span-2">
        <div className="table-toolbar">
          <div className="search-box">
            <Search size={17} />
            <input onChange={(event) => setQuery(event.target.value)} placeholder="Tìm theo huyện, xã, thôn, mô tả..." value={query} />
          </div>
          <select onChange={(event) => setDistrict(event.target.value)} value={district}>
            <option value="">Tất cả huyện</option>
            {districts.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <select onChange={(event) => setScale(event.target.value)} value={scale}>
            <option value="">Tất cả quy mô</option>
            {scales.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Huyện</th>
                <th>Xã</th>
                <th>Thôn</th>
                <th>Diện tích</th>
                <th>Quy mô</th>
                <th>Nguồn</th>
                <th>Ngày ghi nhận</th>
              </tr>
            </thead>
            <tbody>
              {filteredPoints.map((point) => (
                <tr key={point.id}>
                  <td>#{point.id}</td>
                  <td>{point.huyen || "Chưa rõ"}</td>
                  <td>{point.xa || ""}</td>
                  <td>{point.thon || ""}</td>
                  <td>{Number(point.dien_tich || 0).toLocaleString("vi-VN")} m2</td>
                  <td>{point.quy_mo || "Không rõ"}</td>
                  <td>
                    <span className={Number(point.is_new) === 1 ? "tag danger" : "tag"}>
                      {Number(point.is_new) === 1 ? "AI mới" : point.source || "csv"}
                    </span>
                  </td>
                  <td>{point.observed_at || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
