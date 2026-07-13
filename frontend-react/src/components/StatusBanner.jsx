import { AlertTriangle, CheckCircle2, Info, Loader2 } from "lucide-react";

const iconByType = {
  error: AlertTriangle,
  success: CheckCircle2,
  loading: Loader2,
  info: Info,
};

export default function StatusBanner({ status, onClose }) {
  if (!status?.message) return null;
  const Icon = iconByType[status.type] || Info;
  return (
    <div className={`status-banner ${status.type || "info"}`} role="status">
      <Icon className={status.type === "loading" ? "spin" : ""} size={18} />
      <span>{status.message}</span>
      {onClose && status.type !== "loading" ? (
        <button type="button" onClick={onClose} aria-label="Đóng thông báo">
          Đóng
        </button>
      ) : null}
    </div>
  );
}
