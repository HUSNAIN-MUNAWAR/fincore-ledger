"use client";

import { AppShell } from "@/components/app-shell";
import { Card, CardHeader, SecondaryButton } from "@/components/ui";
import { api, clearSession } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { KeyRound, LockKeyhole, LogOut, ShieldCheck, Smartphone } from "lucide-react";
import { useRouter } from "next/navigation";

type Me = { id: string; email: string; full_name: string; status: string; email_verified: boolean; created_at: string };

export default function SettingsPage() {
  const router = useRouter();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/auth/me") });
  const logout = () => { clearSession(); router.replace("/login"); };
  return <AppShell title="Profile and security" eyebrow="Identity controls"><div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]"><Card><CardHeader title="Signed-in identity" description="Authentication context for the active tenant membership." /><div className="p-5"><div className="grid h-14 w-14 place-items-center rounded-2xl bg-slate-950 text-lg font-semibold text-white">{me.data?.full_name?.split(" ").map((part) => part[0]).join("").slice(0,2) ?? "FC"}</div><h2 className="mt-4 text-xl font-semibold">{me.data?.full_name ?? "Loading…"}</h2><p className="mt-1 text-sm text-slate-500">{me.data?.email}</p><div className="mt-5 space-y-3 text-sm"><div className="flex items-center justify-between rounded-xl bg-slate-50 p-3"><span className="text-slate-500">Account status</span><span className="font-semibold capitalize text-emerald-700">{me.data?.status ?? "—"}</span></div><div className="flex items-center justify-between rounded-xl bg-slate-50 p-3"><span className="text-slate-500">Email verification</span><span className="font-semibold">{me.data?.email_verified ? "Verified" : "Pending"}</span></div></div><SecondaryButton className="mt-5 w-full gap-2" onClick={logout}><LogOut size={16} /> Sign out locally</SecondaryButton></div></Card><div className="space-y-6"><Card><CardHeader title="Security architecture" description="Controls implemented by the backend rather than simulated in the interface." /><div className="grid gap-4 p-5 sm:grid-cols-2">{[
    [LockKeyhole, "Argon2 credentials", "Passwords are hashed with memory-hard Argon2 and never logged."],
    [Smartphone, "Rotating sessions", "Refresh tokens are random, hashed in storage, revocable, and rotated."],
    [KeyRound, "Scoped API keys", "Merchant keys are shown once and stored only as secure hashes."],
    [ShieldCheck, "Permission checks", "Authorization runs at route and financial service boundaries."],
  ].map(([Icon, title, detail]) => { const Component = Icon as typeof ShieldCheck; return <div key={String(title)} className="rounded-2xl border border-slate-200 p-4"><span className="grid h-9 w-9 place-items-center rounded-xl bg-slate-100 text-slate-700"><Component size={17} /></span><p className="mt-3 font-semibold">{String(title)}</p><p className="mt-1 text-sm leading-6 text-slate-500">{String(detail)}</p></div>; })}</div></Card><Card><CardHeader title="Production hardening notice" description="FinCore is a reference implementation, not a compliance certification." /><div className="p-5 text-sm leading-7 text-slate-600"><p>A real deployment requires jurisdiction-specific licensing, KYC/AML policy, official provider onboarding, managed secrets, encryption and backup controls, penetration testing, SIEM integration, retention policy, incident response, and independent financial controls review.</p><p className="mt-3 font-medium text-slate-900">The application intentionally stores no card number, CVV, or online-banking credential.</p></div></Card></div></div></AppShell>;
}
