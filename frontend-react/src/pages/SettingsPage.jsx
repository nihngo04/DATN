import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { saveSettings } from "../api/client.js";

export default function SettingsPage({ settings, setSettings, setStatus }) {
  const [form, setForm] = useState({
    force_duplicate: false,
    tile_provider: "esri",
    custom_tile_url: "",
  });

  useEffect(() => {
    if (!settings) return;
    setForm({
      force_duplicate: Boolean(settings.force_duplicate),
      tile_provider: settings.tile_provider || "esri",
      custom_tile_url: settings.custom_tile_url || "",
    });
  }, [settings]);

  async function submit(event) {
    event.preventDefault();
    try {
      setStatus({ type: "loading", message: "Đang lưu setting..." });
      const next = await saveSettings(form);
      setSettings(next);
      setStatus({ type: "success", message: "Đã lưu setting." });
    } catch (error) {
      setStatus({ type: "error", message: error.message });
    }
  }

  return (
    <section className="page-grid settings-grid">
      <div className="page-header">
        <div>
          <p className="eyebrow">Cấu hình workflow</p>
          <h1>Setting hệ thống</h1>
        </div>
      </div>

      <form className="panel settings-form" onSubmit={submit}>
        <div className="panel-heading">
          <div>
            <h2>Luồng phát hiện</h2>
            <p>Điều khiển chế độ test điểm trùng/điểm mới và nền bản đồ vệ tinh.</p>
          </div>
        </div>

        <label className="switch-row">
          <input
            checked={form.force_duplicate}
            onChange={(event) => setForm((value) => ({ ...value, force_duplicate: event.target.checked }))}
            type="checkbox"
          />
          <span>Mặc định tạo kết quả trùng điểm cũ</span>
        </label>

        <label className="field">
          <span>Nguồn bản đồ vệ tinh</span>
          <select
            onChange={(event) => setForm((value) => ({ ...value, tile_provider: event.target.value }))}
            value={form.tile_provider}
          >
            <option value="esri">Esri World Imagery</option>
            <option value="google">Google satellite tile</option>
            <option value="custom">Custom tile URL</option>
          </select>
        </label>

        <label className="field">
          <span>Custom tile URL</span>
          <input
            disabled={form.tile_provider !== "custom"}
            onChange={(event) => setForm((value) => ({ ...value, custom_tile_url: event.target.value }))}
            placeholder="https://.../{z}/{x}/{y}.png"
            value={form.custom_tile_url}
          />
        </label>

        <button className="primary-button" type="submit">
          <Save size={17} />
          Lưu setting
        </button>
      </form>

      <div className="panel">
        <div className="panel-heading">
          <div>
            <h2>Thông tin backend</h2>
            <p>Các giá trị này lấy từ API `/api/settings`.</p>
          </div>
        </div>
        <div className="info-list">
          <div>
            <span>Predict ảnh</span>
            <strong>{settings?.predict_image_url || "Chưa cấu hình"}</strong>
          </div>
          <div>
            <span>Kích thước pixel</span>
            <strong>{settings?.pixel_size_m ?? 4.7} m/pixel</strong>
          </div>
          <div>
            <span>Ngưỡng trùng</span>
            <strong>{settings?.duplicate_distance_m ?? 150} m</strong>
          </div>
        </div>
      </div>
    </section>
  );
}
