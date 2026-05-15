import type { RunStatus } from "../types/api";

const statusClass: Record<RunStatus, string> = {
  pending: "badge-gray",
  queued: "badge-gray",
  running: "badge-blue",
  paused: "badge-yellow",
  partially_paused: "badge-yellow",
  awaiting_approval: "badge-yellow",
  completed: "badge-green",
  failed: "badge-red",
  cancelled: "badge-gray",
  skipped: "badge-gray",
  auto_approved: "badge-green",
  auto_rejected: "badge-red",
};

export default function StatusBadge({ status }: { status?: string }) {
  const normalized = (status || "pending") as RunStatus;
  return <span className={statusClass[normalized] || "badge-gray"}>{status || "pending"}</span>;
}
