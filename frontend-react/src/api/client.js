export const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export function mediaUrl(path) {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path}`;
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const message = typeof payload === "string" ? payload : payload?.detail || "API request failed";
    throw new Error(message);
  }
  return payload;
}

export async function getJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  return parseResponse(response);
}

export async function postForm(path, fields) {
  const form = new FormData();
  Object.entries(fields).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    form.append(key, value);
  });
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body: form,
  });
  return parseResponse(response);
}

export function loadDashboardData() {
  return Promise.all([
    getJson("/api/settings"),
    getJson("/api/stats"),
    getJson("/api/points"),
    getJson("/api/boundary"),
    getJson("/api/boundary/huyen"),
    getJson("/api/rasters"),
    getJson("/api/susceptibility/maps/latest"),
    getJson("/api/susceptibility/maps"),
    getJson("/api/segment-samples"),
  ]).then(([settings, stats, points, boundary, districts, rasters, lsm, susceptibilityMaps, samples]) => {
    const sortedMaps = [...(susceptibilityMaps || [])].sort((a, b) => {
      const bTime = new Date(`${b.created_at || ""}Z`).getTime() || 0;
      const aTime = new Date(`${a.created_at || ""}Z`).getTime() || 0;
      return bTime - aTime || Number(b.id || 0) - Number(a.id || 0);
    });
    return {
      settings,
      stats,
      points,
      boundary,
      districts,
      rasters,
      lsm,
      susceptibilityMaps: sortedMaps,
      samples,
    };
  });
}

export function saveSettings(values) {
  return postForm("/api/settings", values);
}

export function detectFile({ file, forceDuplicate, updateSusceptibility = true }) {
  return postForm("/api/workflows/detect", {
    file,
    force_duplicate: forceDuplicate,
    update_susceptibility: updateSusceptibility,
  });
}

export function detectSegmentSample({ sampleName, forceDuplicate, updateSusceptibility = true }) {
  return postForm("/api/workflows/detect-segment-sample", {
    sample_name: sampleName,
    force_duplicate: forceDuplicate,
    update_susceptibility: updateSusceptibility,
  });
}

export function createSusceptibilityMap({ forceNew = true } = {}) {
  return postForm("/api/susceptibility/maps", { force_new: forceNew });
}

export function listSusceptibilityMaps() {
  return getJson("/api/susceptibility/maps");
}

export function createReport() {
  return postForm("/api/reports", {});
}
