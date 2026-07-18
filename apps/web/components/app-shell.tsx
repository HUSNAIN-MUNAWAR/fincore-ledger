"use client";

import { clearSession, getToken } from "@/lib/api";
import {
  Activity, BookOpenCheck, Building2, ChevronRight, CircleDollarSign, CreditCard,
  KeyRound, LayoutDashboard, LogOut, Menu, RefreshCw, Settings, WalletCards, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";

const nav = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/transactions", label: "Transactions", icon: CircleDollarSign },
  { href: "/withdrawals", label: "Withdrawals", icon: WalletCards },
  { href: "/ledger", label: "Ledger explorer", icon: BookOpenCheck },
  { href: "/reconciliation", label: "Reconciliation", icon: RefreshCw },
  { href: "/webhooks", label: "Webhooks & API", icon: KeyRound },
  { href: "/settings", label: "Security", icon: Settings },
];

export function AppShell({ children, title, eyebrow = "Operations workspace" }: { children: ReactNode; title: string; eyebrow?: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  useEffect(() => { if (!getToken()) router.replace("/login"); }, [router]);
  const logout = () => { clearSession(); router.replace("/login"); };
  return <div className="min-h-screen bg-[#f3f5f8] text-slate-950">
    <button aria-label="Open navigation" onClick={() => setOpen(true)} className="fixed left-4 top-4 z-40 rounded-xl border bg-white p-2 shadow md:hidden"><Menu size={20} /></button>
    {open && <button aria-label="Close navigation overlay" className="fixed inset-0 z-40 bg-slate-950/30 md:hidden" onClick={() => setOpen(false)} />}
    <aside className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col bg-[#08111f] text-slate-200 transition-transform md:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
      <div className="flex h-20 items-center justify-between border-b border-white/10 px-6"><Link href="/dashboard" className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-400 text-slate-950"><CreditCard size={21} /></span><div><p className="font-semibold text-white">FinCore Ledger</p><p className="text-xs text-slate-400">Control plane</p></div></Link><button onClick={() => setOpen(false)} className="md:hidden"><X /></button></div>
      <nav className="flex-1 space-y-1 px-3 py-5">{nav.map(({ href, label, icon: Icon }) => { const active = pathname === href; return <Link key={href} href={href} onClick={() => setOpen(false)} className={`flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium ${active ? "bg-white text-slate-950" : "text-slate-300 hover:bg-white/10 hover:text-white"}`}><Icon size={18} /><span>{label}</span>{active && <ChevronRight className="ml-auto" size={16} />}</Link>; })}</nav>
      <div className="border-t border-white/10 p-4"><div className="mb-3 rounded-xl bg-white/5 p-3"><div className="flex items-center gap-2 text-xs text-emerald-300"><Activity size={14} /> Development provider</div><p className="mt-1 text-xs leading-5 text-slate-400">All external funding and payout confirmations are test-mode only.</p></div><button onClick={logout} className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium text-slate-300 hover:bg-white/10 hover:text-white"><LogOut size={18} /> Sign out</button></div>
    </aside>
    <main className="md:pl-72"><header className="border-b border-slate-200 bg-white/90 px-5 py-6 backdrop-blur md:px-8"><div className="mx-auto max-w-7xl"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">{eyebrow}</p><div className="mt-1 flex items-center justify-between"><h1 className="text-2xl font-semibold tracking-tight text-slate-950 md:text-3xl">{title}</h1><div className="hidden items-center gap-2 rounded-full border border-slate-200 px-3 py-1.5 text-xs text-slate-600 sm:flex"><Building2 size={14} /> Tenant isolated</div></div></div></header><div className="mx-auto max-w-7xl p-5 md:p-8">{children}</div></main>
  </div>;
}
