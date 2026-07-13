import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { mediaUrl } from "../api/client.js";

const QUANG_TRI_CENTER = [16.75, 107.08];

function baseLayerFor(settings) {
  const provider = settings?.tile_provider || "esri";
  if (provider === "custom" && settings?.custom_tile_url) {
    return L.tileLayer(settings.custom_tile_url, {
      maxZoom: 20,
      attribution: "Custom tile",
    });
  }
  if (provider === "google") {
    return L.tileLayer("https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", {
      maxZoom: 20,
      attribution: "Google satellite",
    });
  }
  return L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 19,
      attribution: "Esri World Imagery",
    },
  );
}

function formatArea(value) {
  const area = Number(value || 0);
  return `${area.toLocaleString("vi-VN", { maximumFractionDigits: 1 })} m2`;
}

function pointPopup(point, isNew) {
  return `
    <div class="popup">
      <strong>${isNew ? "Diem AI moi" : "Diem kiem ke"}</strong>
      <div>Huyen: ${point.huyen || "Chua ro"}</div>
      <div>Xa: ${point.xa || "Chua cap nhat"}</div>
      <div>Thon: ${point.thon || "Chua cap nhat"}</div>
      <div>Dien tich: ${formatArea(point.dien_tich)}</div>
      <div>Quy mo: ${point.quy_mo || "Chua ro"}</div>
      <div>Ngay ghi nhan: ${point.observed_at || "Khong co du lieu"}</div>
    </div>
  `;
}

export default function MapView({
  settings,
  points = [],
  boundary,
  districts,
  lsm,
  focusPoint,
  savedView,
  onViewChange,
  showLsm = false,
  height = "100%",
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const layersRef = useRef({});
  const [visible, setVisible] = useState({
    points: true,
    boundary: true,
    districts: true,
    lsm: showLsm,
  });
  const [lsmOpacity, setLsmOpacity] = useState(0.68);

  const pointBounds = useMemo(() => {
    const valid = points.filter((point) => Number(point.lat) && Number(point.lon));
    if (!valid.length) return null;
    return L.latLngBounds(valid.map((point) => [Number(point.lat), Number(point.lon)]));
  }, [points]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    mapRef.current = L.map(containerRef.current, {
      center: savedView?.center || QUANG_TRI_CENTER,
      zoom: savedView?.zoom || 10,
      zoomControl: true,
      preferCanvas: true,
    });

    const saveView = () => {
      if (!onViewChange || !mapRef.current) return;
      const center = mapRef.current.getCenter();
      onViewChange({
        center: [center.lat, center.lng],
        zoom: mapRef.current.getZoom(),
        focusId: focusPoint?.focusId || savedView?.focusId || null,
      });
    };

    mapRef.current.on("moveend zoomend", saveView);
    return () => {
      mapRef.current?.off("moveend zoomend", saveView);
      mapRef.current?.remove();
      mapRef.current = null;
      layersRef.current = {};
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    layersRef.current.base?.remove();
    layersRef.current.base = baseLayerFor(settings).addTo(map);
  }, [settings]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    layersRef.current.boundary?.remove();
    if (visible.boundary && boundary?.features?.length) {
      layersRef.current.boundary = L.geoJSON(boundary, {
        style: {
          color: "#ffffff",
          weight: 3,
          opacity: 0.95,
          fillColor: "#22c55e",
          fillOpacity: 0.04,
        },
      }).addTo(map);
      if (!pointBounds && !savedView) {
        map.fitBounds(layersRef.current.boundary.getBounds(), { padding: [18, 18] });
      }
    }
  }, [boundary, pointBounds, savedView, visible.boundary]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    layersRef.current.districts?.remove();
    if (visible.districts && districts?.features?.length) {
      layersRef.current.districts = L.geoJSON(districts, {
        style: {
          color: "#f8fafc",
          weight: 1,
          opacity: 0.8,
          fillOpacity: 0,
        },
        onEachFeature: (feature, layer) => {
          const name =
            feature.properties?.ten_huyen ||
            feature.properties?.huyen ||
            feature.properties?.name ||
            "Huyen";
          layer.bindTooltip(String(name), { sticky: true });
        },
      }).addTo(map);
    }
  }, [districts, visible.districts]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    layersRef.current.points?.remove();
    if (visible.points) {
      const group = L.layerGroup();
      points.forEach((point) => {
        const lat = Number(point.lat);
        const lon = Number(point.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
        const isNew = Number(point.is_new) === 1 || point.is_new === true;
        const marker = L.circleMarker([lat, lon], {
          radius: isNew ? 8 : 6,
          color: isNew ? "#ef4444" : "#38bdf8",
          weight: 2,
          fillColor: isNew ? "#ef4444" : "#0ea5e9",
          fillOpacity: 0.78,
        });
        marker.bindPopup(pointPopup(point, isNew));
        marker.addTo(group);
      });
      layersRef.current.points = group.addTo(map);
      if (pointBounds && !focusPoint && !savedView) {
        map.fitBounds(pointBounds, { padding: [28, 28], maxZoom: 11 });
      }
    }
  }, [focusPoint, pointBounds, points, savedView, visible.points]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    layersRef.current.lsm?.remove();
    if (visible.lsm && showLsm && lsm?.overlay_url && lsm?.bbox) {
      const bounds = [
        [Number(lsm.bbox.south), Number(lsm.bbox.west)],
        [Number(lsm.bbox.north), Number(lsm.bbox.east)],
      ];
      layersRef.current.lsm = L.imageOverlay(mediaUrl(lsm.overlay_url), bounds, {
        opacity: lsmOpacity,
        interactive: true,
      }).addTo(map);
      map.fitBounds(bounds, { padding: [20, 20] });
    }
  }, [lsm, lsmOpacity, showLsm, visible.lsm]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focusPoint?.lat || !focusPoint?.lon) return;
    if (focusPoint.focusId && savedView?.focusId === focusPoint.focusId) return;

    const target = [Number(focusPoint.lat), Number(focusPoint.lon)];
    map.flyTo(target, 15, { duration: 1.1 });
    if (onViewChange) {
      onViewChange({
        center: target,
        zoom: 15,
        focusId: focusPoint.focusId || null,
      });
    }
    L.popup()
      .setLatLng(target)
      .setContent(
        `<div class="popup"><strong>Vi tri phat hien moi</strong><div>${focusPoint.huyen || "Chua ro huyen"}</div><div>${formatArea(focusPoint.dien_tich)}</div></div>`,
      )
      .openOn(map);
  }, [focusPoint, onViewChange, savedView]);

  return (
    <div className="map-shell" style={{ height }}>
      <div className="map-toolbar">
        <label>
          <input
            checked={visible.points}
            onChange={(event) => setVisible((value) => ({ ...value, points: event.target.checked }))}
            type="checkbox"
          />
          Diem sat lo
        </label>
        <label>
          <input
            checked={visible.boundary}
            onChange={(event) => setVisible((value) => ({ ...value, boundary: event.target.checked }))}
            type="checkbox"
          />
          Vung nghien cuu
        </label>
        <label>
          <input
            checked={visible.districts}
            onChange={(event) => setVisible((value) => ({ ...value, districts: event.target.checked }))}
            type="checkbox"
          />
          Huyen
        </label>
        {showLsm ? (
          <>
            <label>
              <input
                checked={visible.lsm}
                onChange={(event) => setVisible((value) => ({ ...value, lsm: event.target.checked }))}
                type="checkbox"
              />
              LSM
            </label>
            <label className="opacity-control">
              Do mo
              <input
                max="0.95"
                min="0.2"
                onChange={(event) => setLsmOpacity(Number(event.target.value))}
                step="0.05"
                type="range"
                value={lsmOpacity}
              />
            </label>
          </>
        ) : null}
      </div>
      <div className="leaflet-map" ref={containerRef} />
      {showLsm ? (
        <div className="map-legend">
          <span className="legend very-low" /> Rat thap
          <span className="legend low" /> Thap
          <span className="legend mid" /> Trung binh
          <span className="legend high" /> Cao
          <span className="legend very-high" /> Rat cao
        </div>
      ) : null}
    </div>
  );
}
