import { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-slate-200 bg-white shadow-panel ${className}`}>{children}</section>;
}
export function CardHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4"><div><h2 className="font-semibold text-slate-950">{title}</h2>{description && <p className="mt-1 text-sm text-slate-500">{description}</p>}</div>{action}</div>;
}
export function Button({ children, className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={`inline-flex items-center justify-center rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 ${className}`} {...props}>{children}</button>;
}
export function SecondaryButton({ children, className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={`inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50 ${className}`} {...props}>{children}</button>;
}
export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-slate-400 focus:ring-4 focus:ring-slate-100" {...props} />;
}
export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-950 outline-none focus:border-slate-400 focus:ring-4 focus:ring-slate-100" {...props} />;
}
export function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  return <label className="block"><span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>{children}{error && <span className="mt-1 block text-xs text-rose-600">{error}</span>}</label>;
}
export function Empty({ title, detail }: { title: string; detail: string }) {
  return <div className="px-6 py-14 text-center"><p className="font-medium text-slate-800">{title}</p><p className="mt-1 text-sm text-slate-500">{detail}</p></div>;
}
