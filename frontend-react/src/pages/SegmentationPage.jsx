import { useMemo, useState } from "react";
import { Eye, Film, ImageUp, Loader2, Play, RefreshCw, ScanLine } from "lucide-react";
import { detectFile, detectSegmentSample, mediaUrl } from "../api/client.js";

function ResultAlert({ result, onViewLocation }) {
  if (!result) return null;
  return (
    <div className={`decision-box ${result.decision}`}>
      <div>
        <strong>{result.alert || "Da co ket qua phat hien."}</strong>
        <span>
          {result.point
            ? `${result.point.huyen || "Chua ro huyen"} - ${Number(result.point.dien_tich || 0).toLocaleString("vi-VN", {
                maximumFractionDigits: 1,
              })} m2`
            : "Khong co diem vi tri trong phan hoi."}
        </span>
      </div>
      {result.point ? (
        <button className="primary-button" onClick={() => onViewLocation(result.point)} type="button">
          <Eye size={17} />
          Xem vi tri
        </button>
      ) : null}
    </div>
  );
}

function ImageFrame({ title, src, note }) {
  return (
    <div className="media-frame">
      <div className="media-title">
        <strong>{title}</strong>
        {note ? <span>{note}</span> : null}
      </div>
      {src ? <img alt={title} src={mediaUrl(src)} /> : <div className="empty-media">Chua co du lieu</div>}
    </div>
  );
}

function formatMetric(value, suffix = "", digits = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return value ?? "N/A";
  return `${number.toLocaleString("vi-VN", { maximumFractionDigits: digits })}${suffix}`;
}

function VideoStats({ summary }) {
  if (!summary) return null;
  const maxFrames =
    summary.max_frames && summary.source_total_frames && Number(summary.max_frames) >= Number(summary.source_total_frames)
      ? "Toan bo video"
      : summary.max_frames ?? "Khong gioi han";
  const rows = [
    ["Class", summary.class_name || "landslide"],
    ["Threshold", summary.threshold],
    ["Do phan giai", summary.video_width && summary.video_height ? `${summary.video_width} x ${summary.video_height}` : "N/A"],
    ["FPS nguon", formatMetric(summary.source_fps, " fps")],
    ["FPS output", formatMetric(summary.output_fps, " fps")],
    ["Frame xu ly", summary.processed_frames],
    ["Tong frame nguon", summary.source_total_frames],
    ["Stride", summary.frame_stride],
    ["Max frame", maxFrames],
    ["Latency request", formatMetric(summary.request_latency_seconds, "s")],
    ["Thoi gian model", formatMetric(summary.inference_time_seconds, "s")],
    ["Toc do model", formatMetric(summary.effective_fps, " fps")],
    ["Toc do end-to-end", formatMetric(summary.wall_fps, " fps")],
    ["Xac suat max", formatMetric(summary.max_probability)],
    ["Ty le vung TB", formatMetric(Number(summary.average_landslide_area_ratio || 0) * 100, "%")],
    ["Dien tich pixel", formatMetric(summary.total_landslide_area_pixels, " px", 0)],
  ];
  return (
    <div className="metric-grid compact">
      {rows.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value ?? "N/A"}</strong>
        </div>
      ))}
    </div>
  );
}

function videoDisplayUrl(result) {
  return result.output_browser_video_url || result.output_video_url;
}

export default function SegmentationPage({
  settings,
  samples,
  refreshData,
  setStatus,
  setLastResult,
  segmentationOutput,
  setSegmentationOutput,
  onViewLocation,
}) {
  const [imageFile, setImageFile] = useState(null);
  const [videoFile, setVideoFile] = useState(null);
  const [selectedSample, setSelectedSample] = useState("");
  const [forceDuplicate, setForceDuplicate] = useState(Boolean(settings?.force_duplicate));
  const [updateMap, setUpdateMap] = useState(true);
  const [loading, setLoading] = useState("");
  const result = segmentationOutput?.result || null;
  const resultMode = segmentationOutput?.mode || "";
  const currentVideoUrl = result && resultMode === "video" ? videoDisplayUrl(result) : "";

  const sample = useMemo(
    () => samples.find((item) => item.name === selectedSample) || samples[0],
    [samples, selectedSample],
  );

  function clearOutput() {
    setSegmentationOutput({ result: null, mode: "" });
  }

  async function runAction(type) {
    try {
      setLoading(type);
      clearOutput();
      const isVideo = type === "video";
      setStatus({
        type: "loading",
        message: isVideo
          ? "Dang gui video toi /predict-video. Tac vu nay co the mat 20-60 giay hoac lau hon tuy so frame."
          : "Dang resize anh ve 512x512 va goi endpoint phan doan.",
      });

      let response;
      if (type === "sample") {
        if (!sample?.name) throw new Error("Chua co anh test trong data/segment.");
        response = await detectSegmentSample({
          sampleName: sample.name,
          forceDuplicate,
          updateSusceptibility: updateMap,
        });
      } else {
        const file = isVideo ? videoFile : imageFile;
        if (!file) throw new Error(isVideo ? "Chua chon video." : "Chua chon anh.");
        response = await detectFile({
          file,
          forceDuplicate,
          updateSusceptibility: updateMap,
        });
      }

      setSegmentationOutput({ result: response, mode: type });
      setLastResult(response);
      await refreshData(true);
      setStatus({
        type: response.decision === "new" ? "success" : "info",
        message: response.alert || "Da xu ly xong.",
      });
    } catch (error) {
      setStatus({ type: "error", message: error.message });
    } finally {
      setLoading("");
    }
  }

  return (
    <section className="page-grid segmentation-grid">
      <div className="page-header span-2">
        <div>
          <p className="eyebrow">SegFormer-B1 inference</p>
          <h1>Phan doan sat lo tu anh, anh test va video</h1>
        </div>
      </div>

      <div className="panel controls-panel">
        <div className="panel-heading">
          <div>
            <h2>Thiet lap chay thu</h2>
            <p>Chon che do trung diem cu hoac phat hien diem moi. Anh upload luon duoc backend resize ve 512x512 truoc khi predict.</p>
          </div>
        </div>
        <label className="switch-row">
          <input checked={forceDuplicate} onChange={(event) => setForceDuplicate(event.target.checked)} type="checkbox" />
          <span>Tao ket qua trung diem cu</span>
        </label>
        <label className="switch-row">
          <input checked={updateMap} onChange={(event) => setUpdateMap(event.target.checked)} type="checkbox" />
          <span>Cap nhat ban do nhay cam khi phat hien diem moi</span>
        </label>
        <div className="hint-box">
          <strong>Endpoint hien tai</strong>
          <span>{settings?.predict_image_url || "Chua cau hinh"}</span>
        </div>
      </div>

      <div className="panel action-panel">
        <div className="run-card">
          <div className="run-icon">
            <ImageUp size={20} />
          </div>
          <div className="run-content">
            <strong>Upload anh</strong>
            <span>Tra ve layout gom anh dau vao va ket qua phan doan.</span>
            <input accept="image/*,.tif,.tiff" onChange={(event) => setImageFile(event.target.files?.[0] || null)} type="file" />
          </div>
          <button disabled={Boolean(loading)} onClick={() => runAction("image")} type="button">
            {loading === "image" ? <Loader2 className="spin" size={17} /> : <Play size={17} />}
            Predict anh upload
          </button>
        </div>

        <div className="run-card">
          <div className="run-icon">
            <ScanLine size={20} />
          </div>
          <div className="run-content">
            <strong>Anh test trong data/segment</strong>
            <span>Tra ve layout gom anh dau vao, nhan va anh phan doan.</span>
            <select onChange={(event) => setSelectedSample(event.target.value)} value={sample?.name || ""}>
              {samples.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <button disabled={Boolean(loading) || !sample} onClick={() => runAction("sample")} type="button">
            {loading === "sample" ? <Loader2 className="spin" size={17} /> : <Play size={17} />}
            Predict mau / anh test
          </button>
        </div>

        <div className="run-card">
          <div className="run-icon">
            <Film size={20} />
          </div>
          <div className="run-content">
            <strong>Upload video</strong>
            <span>Goi /predict-video va hien thi video overlay truc tiep khi backend tra ket qua.</span>
            <input accept="video/*,.mp4,.mov,.avi,.mkv,.webm" onChange={(event) => setVideoFile(event.target.files?.[0] || null)} type="file" />
          </div>
          <button disabled={Boolean(loading)} onClick={() => runAction("video")} type="button">
            {loading === "video" ? <Loader2 className="spin" size={17} /> : <Play size={17} />}
            Predict video
          </button>
        </div>
      </div>

      <div className="panel span-2">
        <div className="panel-heading">
          <div>
            <h2>Ket qua phan doan</h2>
            <p>Moi nut predict co layout output rieng. Tab khong tu hien anh mau khi moi load.</p>
          </div>
          <button className="ghost-button" disabled={Boolean(loading)} onClick={clearOutput} type="button">
            <RefreshCw size={16} />
            Lam moi khung xem
          </button>
        </div>

        <ResultAlert result={result} onViewLocation={onViewLocation} />

        {!result ? (
          <div className="output-placeholder">
            Chon mot che do predict o phia tren de xem ket qua. Khung nay khong tu hien thi output mau khi moi mo tab.
          </div>
        ) : null}

        {result && resultMode === "image" ? (
          <div className="media-grid two-columns">
            <ImageFrame note="Anh upload da resize 512x512" src={result.preprocessed_image_url} title="Anh dau vao" />
            <ImageFrame note="Mask du doan mau do" src={result.output_image_url} title="Ket qua phan doan" />
          </div>
        ) : null}

        {result && resultMode === "sample" ? (
          <div className="media-grid">
            <ImageFrame note="Anh test da resize 512x512" src={result.preprocessed_image_url} title="Anh dau vao" />
            <ImageFrame note="Mask that mau xanh la" src={result.true_mask_url} title="Nhan" />
            <ImageFrame note="Xanh: nhan that, do: du doan" src={result.output_image_url} title="Ket qua phan doan" />
          </div>
        ) : null}

        {result && resultMode === "video" ? (
          <div className="video-result">
            <div className="video-player-frame">
              <div className="media-title">
                <strong>GIF output</strong>
                <span>Preview overlay vung sat lo mau do</span>
              </div>
              {result.output_gif_url ? (
                <>
                  <img alt="GIF preview phan doan video" className="video-gif-output" src={mediaUrl(result.output_gif_url)} />
                  {result.output_video_url ? (
                    <a className="video-open-link" href={mediaUrl(result.output_video_url)} rel="noreferrer" target="_blank">
                      Mo video da luu trong data/output/video
                    </a>
                  ) : null}
                  {currentVideoUrl && currentVideoUrl !== result.output_video_url ? (
                    <a className="video-open-link secondary" href={mediaUrl(currentVideoUrl)} rel="noreferrer" target="_blank">
                      Mo ban preview MP4/WebM
                    </a>
                  ) : null}
                </>
              ) : (
                <div className="empty-media">Chua co GIF preview</div>
              )}
            </div>
            <VideoStats summary={result.video_summary} />
          </div>
        ) : null}
      </div>
    </section>
  );
}
