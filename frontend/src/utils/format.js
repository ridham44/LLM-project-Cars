export function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

export function formatSeconds(value) {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(1)}s`;
}

export function formatRelativeDate(isoString) {
  if (!isoString) return "—";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "—";

  const diffMs = Date.now() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays <= 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays} days ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function confidenceTone(value) {
  if (value === null || value === undefined) return "neutral";
  if (value >= 0.8) return "success";
  if (value >= 0.55) return "warning";
  return "danger";
}
