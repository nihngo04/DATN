import { useEffect, useMemo, useState } from "react";
import { CalendarClock, Eye, Layers, RefreshCw } from "lucide-react";
import { createSusceptibilityMap } from "../api/client.js";
import MapView from "../components/MapView.jsx";

function formatDateTime(value) {
  if (!value) return "Khong ro thoi gian";
  const normalized = String(value).endsWith("Z") ? value : `${value}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function MapHistory({ maps, activeMap, onSelect }) {
  if (!maps?.length) {
    return <div className="empty-row">Chua co lich su ban do nhay cam.</div>;
  }

  return (
    <div className="map-history-list">
      {maps.map((item) => {
        const active = item.id && activeMap?.id === item.id;
        return (
          <button className={`map-history-item ${active ? "active" : ""}`} key={item.id || item.overlay_url} onClick={() => onSelect(item)} type="button">
            <span className="history-icon">
              {active ? <Eye size={16} /> : <CalendarClock size={16} />}
            </span>
            <span className="history-main">
              <strong>{item.title || `Ban do #${item.id}`}</strong>
              <small>{formatDateTime(item.created_at)}</small>
              {item.message ? <em>{item.message}</em> : null}
            </span>
            <span className="history-status">{item.status || "done"}</span>
          </button>
        );
      })}
    </div>
  );
}

export default function SusceptibilityPage({
  settings,
  points,
  boundary,
  districts,
  lsm,
  rasters,
  susceptibilityMaps = [],
  setStatus,
  refreshData,
  setLsm,
  setSusceptibilityMaps,
}) {
  const [creating, setCreating] = useState(false);
  const [selectedMapId, setSelectedMapId] = useState(lsm?.id || "");

  const sortedMaps = useMemo(
    () =>
      [...susceptibilityMaps].sort((a, b) => {
        const bTime = new Date(`${b.created_at || ""}Z`).getTime() || 0;
        const aTime = new Date(`${a.created_at || ""}Z`).getTime() || 0;
        return bTime - aTime || Number(b.id || 0) - Number(a.id || 0);
      }),
    [susceptibilityMaps],
  );

  useEffect(() => {
    if (lsm?.id) setSelectedMapId(lsm.id);
  }, [lsm?.id]);

  async function regenerate() {
    try {
      setCreating(true);
      setStatus({ type: "loading", message: "Dang tao phien ban ban do nhay cam moi..." });
      const map = await createSusceptibilityMap({ forceNew: true });
      setLsm(map);
      setSelectedMapId(map.id || "");
      const nextData = await refreshData(true);
      if (nextData?.susceptibilityMaps) setSusceptibilityMaps(nextData.susceptibilityMaps);
      setLsm(map);
      setStatus({ type: "success", message: map.message || "Da tao ban do nhay cam moi." });
    } catch (error) {
      setStatus({ type: "error", message: error.message });
    } finally {
      setCreating(false);
    }
  }

  function selectMap(map) {
    setLsm(map);
    setSelectedMapId(map.id || "");
    setStatus({
      type: "info",
      message: `Dang xem ban do: ${map.title || `#${map.id}`} - ${formatDateTime(map.created_at)}`,
    });
  }

  return (
    <section className="page-grid susceptibility-grid">
      <div className="page-header span-2">
        <div>
          <p className="eyebrow">ExtraTrees LSM</p>
          <h1>Ban do nhay cam sat lo</h1>
        </div>
        <button className="primary-button" disabled={creating} onClick={regenerate} type="button">
          <RefreshCw className={creating ? "spin" : ""} size={17} />
          Tao phien ban moi
        </button>
      </div>

      <div className="panel map-panel span-2">
        <div className="panel-heading">
          <div>
            <h2>{lsm?.title || "Chua co ban do nhay cam"}</h2>
            <p>
              {lsm?.created_at ? `Thoi gian tao: ${formatDateTime(lsm.created_at)}. ` : ""}
              {lsm?.message || "Dat GeoTIFF/PNG vao data/susceptibility hoac tao moi tu workflow."}
            </p>
          </div>
          {selectedMapId ? <span className="history-current">Dang xem #{selectedMapId}</span> : null}
        </div>
        <MapView
          boundary={boundary}
          districts={districts}
          lsm={lsm}
          points={points}
          settings={settings}
          showLsm
          height="calc(100vh - 300px)"
        />
      </div>

      <div className="panel">
        <div className="panel-heading">
          <div>
            <h2>Lich su ban do</h2>
            <p>Chon mot phien ban cu de xem lai overlay theo thoi gian.</p>
          </div>
        </div>
        <MapHistory activeMap={lsm} maps={sortedMaps} onSelect={selectMap} />
      </div>

      <div className="panel">
        <div className="panel-heading">
          <div>
            <h2>Thong tin hien thi</h2>
            <p>Quan ly thoi gian tao, nguon raster va bbox cua ban do dang xem.</p>
          </div>
        </div>
        <div className="info-list">
          <div>
            <span>So phien ban</span>
            <strong>{sortedMaps.length}</strong>
          </div>
          <div>
            <span>Thoi gian ban do dang xem</span>
            <strong>{formatDateTime(lsm?.created_at)}</strong>
          </div>
          <div>
            <span>Trang thai</span>
            <strong>{lsm?.status || "empty"}</strong>
          </div>
          <div>
            <span>Overlay</span>
            <strong>{lsm?.overlay_url ? "Co" : "Chua co"}</strong>
          </div>
          <div>
            <span>BBox</span>
            <strong>
              {lsm?.bbox
                ? `${Number(lsm.bbox.west).toFixed(3)}, ${Number(lsm.bbox.south).toFixed(3)} - ${Number(lsm.bbox.east).toFixed(3)}, ${Number(lsm.bbox.north).toFixed(3)}`
                : "Khong co"}
            </strong>
          </div>
        </div>
      </div>

      <div className="panel span-2">
        <div className="panel-heading">
          <div>
            <h2>Lop raster yeu to dieu kien</h2>
            <p>Danh sach raster da dang ky trong SQLite tu thu muc data/raster.</p>
          </div>
        </div>
        <div className="raster-list wide">
          {rasters.map((raster) => (
            <div key={raster.id}>
              <Layers size={16} />
              <span>{raster.name}</span>
              <strong>{raster.factor_type}</strong>
            </div>
          ))}
          {!rasters.length ? <div className="empty-row">Chua co raster duoc dang ky.</div> : null}
        </div>
      </div>
    </section>
  );
}
