import type { RunStatus } from "../types/api";

const statusClass: Record<RunStatus, string> = {
  pending: "badge-gray",
  running: "badge-blue",
  paused: "badge-yellow",
  completed: "badge-green",
  failed: "badge-red",
  cancelled: "badge-gray",
};

export default function StatusBadge({ status }: { status?: string }) {
  const normalized = (status || "pending") as RunStatus;
  return <span className={statusClass[normalized] || "badge-gray"}>{status || "pending"}</span>;
}
