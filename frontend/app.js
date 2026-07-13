const API_BASE = 'http://127.0.0.1:8000';

const tileSources = {
    esri: {
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        options: { maxZoom: 19, attribution: 'Tiles &copy; Esri' }
    },
    google: {
        url: 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
        options: { maxZoom: 20, attribution: 'Satellite imagery' }
    }
};

const map = L.map('map', { zoomControl: true }).setView([16.75, 107.08], 10);
let baseLayer = null;
const labelLayer = L.tileLayer(
    'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
    { maxZoom: 19, attribution: 'Labels &copy; Esri' }
).addTo(map);

const districtLayer = L.layerGroup().addTo(map);
const boundaryLayer = L.layerGroup().addTo(map);
const pointLayer = L.layerGroup().addTo(map);
let susceptibilityLayer = null;

const tabs = document.querySelectorAll('.tab');
const pages = document.querySelectorAll('.page');
const mapControls = document.querySelector('[data-map-control]');
const overviewMapParent = document.querySelector('#page-overview .map-card');
const susceptibilityMapHost = document.getElementById('map-host');
const mapContainer = document.getElementById('map');

const statusLine = document.getElementById('status-line');
const workflowForm = document.getElementById('workflow-form');
const uploadFileInput = document.getElementById('upload-file');
const uploadVideoFileInput = document.getElementById('upload-video-file');
const runVideoButton = document.getElementById('run-video');
const segmentSampleInput = document.getElementById('segment-sample');
const showSegmentSampleButton = document.getElementById('show-segment-sample');
const runSegmentSampleButton = document.getElementById('run-segment-sample');
const updateSusceptibilityInput = document.getElementById('update-susceptibility');
const forceDuplicateInput = document.getElementById('force-duplicate');
const workflowResult = document.getElementById('workflow-result');
const preprocessedImage = document.getElementById('preprocessed-image');
const maskImage = document.getElementById('mask-image');
const outputImage = document.getElementById('output-image');
const outputVideo = document.getElementById('output-video');
const videoDetail = document.getElementById('video-detail');
const detectionDetail = document.getElementById('detection-detail');
const toggleDistricts = document.getElementById('toggle-districts');
const toggleBoundary = document.getElementById('toggle-boundary');
const togglePoints = document.getElementById('toggle-points');
const toggleSusceptibility = document.getElementById('toggle-susceptibility');
const overviewStats = document.getElementById('overview-stats');
const statsBox = document.getElementById('stats-box');
const scaleStats = document.getElementById('scale-stats');
const inventoryTable = document.getElementById('inventory-table');
const rasterList = document.getElementById('raster-list');
const susceptibilityInfo = document.getElementById('susceptibility-info');
const settingsForm = document.getElementById('settings-form');
const settingsInfo = document.getElementById('settings-info');
const tileProviderInput = document.getElementById('tile-provider');
const customTileUrlInput = document.getElementById('custom-tile-url');

let segmentSamples = [];
let currentSettings = {};
let lastDetectedPoint = null;

tabs.forEach(button => {
    button.addEventListener('click', () => activateTab(button.dataset.tab));
});

workflowForm.addEventListener('submit', async event => {
    event.preventDefault();
    const file = uploadFileInput.files[0];
    if (!file) {
        setStatus('Chọn ảnh đầu vào trước.');
        return;
    }
    const formData = predictionForm();
    formData.append('file', file);
    await runPrediction('/api/workflows/detect', formData);
});

showSegmentSampleButton.addEventListener('click', () => {
    const sample = segmentSamples.find(item => item.name === segmentSampleInput.value);
    if (!sample) return;
    setImage(preprocessedImage, sample.image_url);
    setImage(maskImage, sample.mask_url);
    outputImage.classList.remove('visible');
    outputImage.removeAttribute('src');
    detectionDetail.innerHTML = `<dl><dt>Ảnh</dt><dd>${escapeHtml(sample.name)}</dd><dt>Nhãn</dt><dd>Mask từ data/segment/mask</dd></dl>`;
    workflowResult.textContent = 'Đã nạp ảnh và mask mẫu từ data/segment.';
});

runSegmentSampleButton.addEventListener('click', async () => {
    if (!segmentSampleInput.value) {
        setStatus('Không có ảnh mẫu trong data/segment.');
        return;
    }
    const formData = predictionForm();
    formData.append('sample_name', segmentSampleInput.value);
    await runPrediction('/api/workflows/detect-segment-sample', formData);
});

runVideoButton.addEventListener('click', async () => {
    const file = uploadVideoFileInput.files[0];
    if (!file) {
        setStatus('Chọn video đầu vào trước.');
        return;
    }
    const formData = predictionForm();
    formData.append('file', file);
    await runPrediction('/api/workflows/detect', formData, 'video');
});

document.addEventListener('click', event => {
    if (event.target && event.target.id === 'view-location' && lastDetectedPoint) {
        activateTab('overview');
        map.flyTo([lastDetectedPoint.lat, lastDetectedPoint.lon], 15, { duration: 0.9 });
    }
});

settingsForm.addEventListener('submit', async event => {
    event.preventDefault();
    const formData = new FormData();
    formData.append('force_duplicate', forceDuplicateInput.checked ? 'true' : 'false');
    formData.append('tile_provider', tileProviderInput.value);
    formData.append('custom_tile_url', customTileUrlInput.value.trim());
    const data = await postForm('/api/settings', formData);
    if (data) {
        applySettings(data);
        renderSettings(data);
    }
});

document.getElementById('refresh-stats').addEventListener('click', refreshStats);

document.getElementById('create-report').addEventListener('click', async () => {
    const data = await postForm('/api/reports', new FormData());
    if (!data) return;
    statsBox.innerHTML = `${statsHtml(data.stats)}<p><a href="${API_BASE}${data.report_url}" target="_blank">Mở báo cáo</a></p>`;
});

document.getElementById('create-susceptibility').addEventListener('click', async () => {
    const data = await postForm('/api/susceptibility/maps', new FormData());
    if (data) renderSusceptibility(data);
});

toggleDistricts.addEventListener('change', () => toggleLayer(districtLayer, toggleDistricts.checked));
toggleBoundary.addEventListener('change', () => toggleLayer(boundaryLayer, toggleBoundary.checked));
togglePoints.addEventListener('change', () => toggleLayer(pointLayer, togglePoints.checked));
toggleSusceptibility.addEventListener('change', () => {
    if (susceptibilityLayer) toggleLayer(susceptibilityLayer, toggleSusceptibility.checked);
});

function predictionForm() {
    const formData = new FormData();
    formData.append('force_duplicate', forceDuplicateInput.checked ? 'true' : 'false');
    formData.append('update_susceptibility', updateSusceptibilityInput.checked ? 'true' : 'false');
    return formData;
}

async function runPrediction(path, formData, mode = 'image') {
    if (mode === 'video') {
        setStatus('Đang gọi /predict-video. Video có thể mất 20-60 giây tùy max_frames và frame_stride...');
    } else {
        setStatus('Đang tiền xử lý ảnh 512 x 512 và gọi mô hình phân đoạn...');
    }
    workflowResult.textContent = 'Đang xử lý...';
    const data = await postForm(path, formData);
    if (!data) return;

    renderDetection(data);
    await refreshPoints();
    await refreshStats();
    if (data.susceptibility_map) renderSusceptibility(data.susceptibility_map);

    if (data.decision === 'new') {
        setStatus(`${data.alert} Bấm "Xem vị trí" để zoom tới điểm mới.`);
    }
}

function activateTab(tabName) {
    tabs.forEach(tab => tab.classList.toggle('active', tab.dataset.tab === tabName));
    pages.forEach(page => page.classList.toggle('active', page.id === `page-${tabName}`));

    const mapVisible = tabName === 'overview' || tabName === 'susceptibility';
    mapControls.style.display = mapVisible ? 'flex' : 'none';
    if (tabName === 'overview' && mapContainer.parentElement !== overviewMapParent) {
        overviewMapParent.appendChild(mapContainer);
    }
    if (tabName === 'susceptibility' && mapContainer.parentElement !== susceptibilityMapHost) {
        susceptibilityMapHost.appendChild(mapContainer);
    }
    if (mapVisible) setTimeout(() => map.invalidateSize(), 60);
}

async function boot() {
    const settings = await getJson('/api/settings');
    if (settings) {
        applySettings(settings);
        renderSettings(settings);
    }
    await refreshSegmentSamples();
    await loadDistricts();
    await loadBoundary();
    await refreshPoints();
    await refreshRasters();
    await refreshStats();
    await loadLatestSusceptibility();
    activateTab('overview');
}

function applySettings(settings) {
    currentSettings = settings;
    forceDuplicateInput.checked = Boolean(settings.force_duplicate);
    tileProviderInput.value = settings.tile_provider || 'esri';
    customTileUrlInput.value = settings.custom_tile_url || '';
    setBaseLayer(settings.tile_provider || 'esri', settings.custom_tile_url || '');
}

function setBaseLayer(provider, customUrl) {
    if (baseLayer) map.removeLayer(baseLayer);
    const source = provider === 'custom' && customUrl
        ? { url: customUrl, options: { maxZoom: 22, attribution: 'Custom imagery' } }
        : tileSources[provider] || tileSources.esri;
    baseLayer = L.tileLayer(source.url, source.options).addTo(map);
    baseLayer.bringToBack();
    labelLayer.bringToFront();
}

function renderSettings(data) {
    settingsInfo.innerHTML = `
        <dl>
            <dt>Predict URL</dt><dd>${escapeHtml(data.predict_image_url)}</dd>
            <dt>Pixel size</dt><dd>${data.pixel_size_m} m/pixel</dd>
            <dt>Chế độ điểm</dt><dd>${data.force_duplicate ? 'Tạo trùng điểm cũ' : 'Lấy từ CSV điểm mới'}</dd>
            <dt>Nguồn ảnh</dt><dd>${escapeHtml(data.tile_provider)}</dd>
        </dl>
    `;
}

async function refreshSegmentSamples() {
    segmentSamples = await getJson('/api/segment-samples') || [];
    segmentSampleInput.innerHTML = segmentSamples.length
        ? segmentSamples.map(row => `<option value="${escapeHtml(row.name)}">${escapeHtml(row.name)}</option>`).join('')
        : '<option value="">Không có mẫu</option>';
}

async function loadDistricts() {
    const geojson = await getJson('/api/boundary/huyen');
    if (!geojson || !geojson.features) return;
    districtLayer.clearLayers();
    const layer = L.geoJSON(geojson, {
        style: { color: '#38bdf8', weight: 1.2, opacity: 0.85, fillOpacity: 0.03 },
        onEachFeature: (feature, layerItem) => layerItem.bindTooltip(feature.properties.name)
    });
    districtLayer.addLayer(layer);
}

async function loadBoundary() {
    const geojson = await getJson('/api/boundary');
    if (!geojson || !geojson.features || !geojson.features.length) return;
    boundaryLayer.clearLayers();
    const layer = L.geoJSON(geojson, {
        style: {
            color: '#fbbf24',
            weight: 3,
            opacity: 1,
            fillColor: '#f59e0b',
            fillOpacity: 0.14,
            dashArray: '8 5'
        }
    }).bindPopup('Vùng nghiên cứu Quảng Trị');
    boundaryLayer.addLayer(layer);
    map.fitBounds(layer.getBounds(), { padding: [28, 28] });
}

async function refreshPoints() {
    const points = await getJson('/api/points');
    if (!points) return;
    pointLayer.clearLayers();
    points.forEach(point => {
        const isNew = Number(point.is_new) === 1;
        L.circleMarker([point.lat, point.lon], {
            radius: isNew ? 7 : 4.5,
            color: '#ffffff',
            fillColor: isNew ? '#ef4444' : '#2563eb',
            fillOpacity: 0.9,
            weight: isNew ? 2.2 : 1.2
        }).bindPopup(pointPopup(point)).addTo(pointLayer);
    });
}

function pointPopup(point) {
    return `
        <strong>${escapeHtml(point.thon || point.huyen || 'Điểm sạt lở')}</strong>
        <dl class="popup-dl">
            <dt>Huyện</dt><dd>${escapeHtml(point.huyen || '-')}</dd>
            <dt>Xã</dt><dd>${escapeHtml(point.xa || '-')}</dd>
            <dt>Diện tích</dt><dd>${Number(point.dien_tich || 0).toLocaleString('vi-VN')} m²</dd>
            <dt>Quy mô</dt><dd>${escapeHtml(point.quy_mo || '-')}</dd>
            <dt>Ngày</dt><dd>${escapeHtml(point.observed_at || '-')}</dd>
        </dl>
    `;
}

function renderDetection(data) {
    lastDetectedPoint = data.point;
    const viewButton = data.decision === 'new'
        ? '<button id="view-location" type="button" class="secondary-action">Xem vị trí</button>'
        : '';
    workflowResult.innerHTML = `
        <dl>
            <dt>Quyết định</dt><dd>${escapeHtml(data.decision)}</dd>
            <dt>Predict</dt><dd>${escapeHtml(data.predict_status)}</dd>
            <dt>Huyện</dt><dd>${escapeHtml(data.point.huyen || '-')}</dd>
            <dt>Tọa độ</dt><dd>${data.point.lat}, ${data.point.lon}</dd>
            <dt>Diện tích</dt><dd>${Number(data.point.dien_tich).toLocaleString('vi-VN')} m²</dd>
        </dl>
        ${viewButton}
    `;
    detectionDetail.innerHTML = `
        <dl>
            <dt>Huyện</dt><dd>${escapeHtml(data.point.huyen || '-')}</dd>
            <dt>Xã</dt><dd>${escapeHtml(data.point.xa || '-')}</dd>
            <dt>Kích thước</dt><dd>${data.prediction.width_m || '-'} x ${data.prediction.height_m || '-'} m</dd>
            <dt>Ngày ghi nhận</dt><dd>${escapeHtml(data.point.observed_at)}</dd>
            <dt>Cảnh báo</dt><dd>${escapeHtml(data.alert)}</dd>
        </dl>
    `;
    setImage(preprocessedImage, data.preprocessed_image_url);
    setImage(maskImage, data.true_mask_url);
    setImage(outputImage, data.output_image_url);
    renderVideoResult(data);
    setStatus(data.alert);
}

function renderVideoResult(data) {
    if (data.media_type !== 'video' || !data.output_video_url) {
        outputVideo.classList.remove('visible');
        outputVideo.removeAttribute('src');
        videoDetail.innerHTML = '';
        return;
    }

    const summary = data.video_summary || data.prediction || {};
    outputVideo.src = `${API_BASE}${data.output_video_url}`;
    outputVideo.classList.add('visible');
    videoDetail.innerHTML = `
        <dl>
            <dt>Frames xử lý</dt><dd>${summary.processed_frames ?? '-'}/${summary.source_total_frames ?? '-'}</dd>
            <dt>Stride</dt><dd>${summary.frame_stride ?? '-'}</dd>
            <dt>Max frames</dt><dd>${summary.max_frames ?? '-'}</dd>
            <dt>FPS</dt><dd>${summary.output_fps ?? summary.source_fps ?? '-'}</dd>
            <dt>Area pixels</dt><dd>${Number(summary.total_landslide_area_pixels || 0).toLocaleString('vi-VN')}</dd>
            <dt>Area ratio TB</dt><dd>${summary.average_landslide_area_ratio ?? '-'}</dd>
            <dt>Max prob</dt><dd>${summary.max_probability ?? '-'}</dd>
            <dt>Latency</dt><dd>${summary.inference_time_seconds ?? '-'} giây</dd>
        </dl>
    `;
}

async function refreshRasters() {
    const rows = await getJson('/api/rasters');
    if (!rows) return;
    rasterList.innerHTML = rows.length
        ? rows.map(row => `<div class="list-row"><strong>${escapeHtml(row.factor_type)}</strong><span>${escapeHtml(row.name)}</span></div>`).join('')
        : 'Chưa có raster.';
}

async function refreshStats() {
    const data = await getJson('/api/stats');
    if (!data) return;
    overviewStats.innerHTML = `
        <div><strong>${data.inventory_total}</strong><span>Điểm kiểm kê</span></div>
        <div><strong>${data.new_inventory_total}</strong><span>Điểm mới AI</span></div>
        <div><strong>${data.detection_jobs_total}</strong><span>Lượt predict</span></div>
        <div><strong>${Number(data.area_total_m2).toLocaleString('vi-VN')}</strong><span>m² ghi nhận</span></div>
    `;
    statsBox.innerHTML = statsHtml(data);
    scaleStats.innerHTML = (data.by_quy_mo || [])
        .map(item => `<div class="list-row"><strong>${escapeHtml(item.quy_mo)}</strong><span>${item.total} điểm</span></div>`)
        .join('');
    inventoryTable.innerHTML = (data.recent || [])
        .map(row => `
            <tr>
                <td>${row.id}</td>
                <td>${escapeHtml(row.huyen || '')}</td>
                <td>${escapeHtml(row.xa || '')}</td>
                <td>${escapeHtml(row.thon || '')}</td>
                <td>${Number(row.dien_tich || 0).toLocaleString('vi-VN')}</td>
                <td>${escapeHtml(row.quy_mo || '')}</td>
                <td>${escapeHtml(row.observed_at || '')}</td>
                <td>${escapeHtml(row.source || '')}</td>
            </tr>
        `).join('');
}

function statsHtml(data) {
    return `
        <dl>
            <dt>Tổng điểm</dt><dd>${data.inventory_total}</dd>
            <dt>Điểm mới AI</dt><dd>${data.new_inventory_total}</dd>
            <dt>Lượt predict</dt><dd>${data.detection_jobs_total}</dd>
            <dt>Predict mới</dt><dd>${data.new_detection_jobs}</dd>
            <dt>Predict trùng</dt><dd>${data.duplicate_detection_jobs}</dd>
            <dt>Tổng diện tích</dt><dd>${Number(data.area_total_m2).toLocaleString('vi-VN')} m²</dd>
        </dl>
        <h3>Theo huyện</h3>
        ${(data.by_huyen || []).map(item => `<div class="list-row"><strong>${escapeHtml(item.huyen)}</strong><span>${item.total}</span></div>`).join('')}
    `;
}

async function loadLatestSusceptibility() {
    const data = await getJson('/api/susceptibility/maps/latest');
    if (data && data.status !== 'empty' && data.overlay_url) renderSusceptibility(data);
}

function renderSusceptibility(data) {
    if (!data.overlay_url || !data.bbox) return;
    const bounds = [[data.bbox.south, data.bbox.west], [data.bbox.north, data.bbox.east]];
    if (susceptibilityLayer) map.removeLayer(susceptibilityLayer);
    susceptibilityLayer = L.imageOverlay(`${API_BASE}${data.overlay_url}`, bounds, { opacity: 0.72 });
    if (toggleSusceptibility.checked) susceptibilityLayer.addTo(map);
    susceptibilityInfo.innerHTML = `
        <dl>
            <dt>Trạng thái</dt><dd>${escapeHtml(data.status)}</dd>
            <dt>Lớp</dt><dd>${escapeHtml(data.title || 'LSM')}</dd>
            <dt>Ghi chú</dt><dd>${escapeHtml(data.message || '')}</dd>
        </dl>
    `;
}

function setImage(element, url) {
    if (!url) {
        element.removeAttribute('src');
        element.classList.remove('visible');
        return;
    }
    element.src = `${API_BASE}${url}`;
    element.classList.add('visible');
}

function toggleLayer(layer, checked) {
    if (checked) layer.addTo(map);
    else map.removeLayer(layer);
}

async function getJson(path) {
    try {
        const response = await fetch(`${API_BASE}${path}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || data.error || response.statusText);
        return data;
    } catch (error) {
        setStatus(error.message);
        return null;
    }
}

async function postForm(path, formData) {
    try {
        const response = await fetch(`${API_BASE}${path}`, { method: 'POST', body: formData });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || data.error || response.statusText);
        return data;
    } catch (error) {
        setStatus(error.message);
        return null;
    }
}

function setStatus(message) {
    statusLine.textContent = message || 'Sẵn sàng';
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

boot();
