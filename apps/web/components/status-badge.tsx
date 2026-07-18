import { humanize } from "@/lib/format";

const positive = new Set(["active", "captured", "completed", "verified", "delivered", "posted", "ready"]);
const caution = new Set(["pending", "processing", "under_review", "requested", "authorized", "partially_refunded", "running"]);
const negative = new Set(["failed", "rejected", "frozen", "restricted", "dead_letter", "cancelled"]);

export function StatusBadge({ value }: { value: string }) {
  const tone = positive.has(value) ? "bg-emerald-50 text-emerald-700 ring-emerald-200" :
    caution.has(value) ? "bg-amber-50 text-amber-700 ring-amber-200" :
    negative.has(value) ? "bg-rose-50 text-rose-700 ring-rose-200" :
    "bg-slate-100 text-slate-700 ring-slate-200";
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${tone}`}>{humanize(value)}</span>;
}
