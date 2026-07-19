"use client";

import { api, setSession } from "@/lib/api";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, LockKeyhole, ShieldCheck, WalletCards } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button, Field, Input } from "@/components/ui";

const schema = z.object({ email: z.string().email(), password: z.string().min(8) });
type FormData = z.infer<typeof schema>;
type LoginResponse = { access_token: string; refresh_token: string; organization_id: string };

export default function LoginPage() {
  const router = useRouter();
  const [serverError, setServerError] = useState("");
  const { register, handleSubmit, formState: { errors, isSubmitting }, setValue } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { email: "customer@fincore.example", password: "FinCore-Dev-2026!" },
  });
  const onSubmit = async (values: FormData) => {
    setServerError("");
    try {
      const result = await api<LoginResponse>("/auth/login", { method: "POST", body: JSON.stringify(values) });
      setSession(result.access_token, result.refresh_token, result.organization_id);
      router.push("/dashboard");
    } catch (error) { setServerError(error instanceof Error ? error.message : "Unable to sign in"); }
  };
  const selectAccount = (email: string) => { setValue("email", email); setValue("password", "FinCore-Dev-2026!"); };
  return <main className="grid min-h-screen bg-[#07111f] lg:grid-cols-[1.1fr_0.9fr]">
    <section className="relative hidden overflow-hidden border-r border-white/10 p-12 text-white lg:flex lg:flex-col lg:justify-between">
      <div className="absolute inset-0 opacity-40" style={{ backgroundImage: "radial-gradient(circle at 20% 20%, rgba(52,211,153,.3), transparent 28%), radial-gradient(circle at 80% 70%, rgba(59,130,246,.25), transparent 32%)" }} />
      <div className="relative"><div className="flex items-center gap-3"><span className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-400 text-slate-950"><WalletCards /></span><div><p className="font-semibold">FinCore Ledger</p><p className="text-xs text-slate-400">Financial operations control plane</p></div></div></div>
      <div className="relative max-w-xl"><p className="text-sm font-semibold uppercase tracking-[0.18em] text-emerald-300">Ledger-first infrastructure</p><h1 className="mt-4 text-5xl font-semibold leading-tight tracking-tight">Money movement that can be explained, reconciled, and audited.</h1><p className="mt-6 max-w-lg text-lg leading-8 text-slate-300">A production-oriented reference platform for wallets, merchant payments, withdrawals, refunds, webhooks, and immutable double-entry accounting.</p><div className="mt-10 grid grid-cols-3 gap-4">{[["Balanced", "Every journal"], ["Scoped", "Every request"], ["Idempotent", "Every command"]].map(([a,b]) => <div key={a} className="rounded-2xl border border-white/10 bg-white/5 p-4"><p className="font-semibold text-white">{a}</p><p className="mt-1 text-xs text-slate-400">{b}</p></div>)}</div></div>
      <div className="relative flex items-center gap-2 text-xs text-slate-400"><ShieldCheck size={16} className="text-emerald-300" /> Engineering reference only — not licensed or certified for unrestricted real-money processing.</div>
    </section>
    <section className="flex items-center justify-center bg-slate-50 p-6 md:p-10"><div className="w-full max-w-md"><div className="mb-8 lg:hidden"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-400"><WalletCards size={20} /></span><p className="font-semibold text-slate-950">FinCore Ledger</p></div></div><div className="rounded-3xl border border-slate-200 bg-white p-7 shadow-panel md:p-9"><div className="mb-7"><span className="grid h-11 w-11 place-items-center rounded-xl bg-slate-100 text-slate-700"><LockKeyhole size={20} /></span><h2 className="mt-5 text-2xl font-semibold tracking-tight">Access your workspace</h2><p className="mt-2 text-sm leading-6 text-slate-500">Choose a development identity for the UCI public dataset demo.</p></div><div className="mb-6 grid grid-cols-2 gap-2">{[["Customer","customer@fincore.example"],["Merchant","merchant@fincore.example"],["Operations","ops@fincore.example"],["Admin","admin@fincore.example"]].map(([label,email]) => <button key={email} onClick={() => selectAccount(email)} className="rounded-xl border border-slate-200 px-3 py-2 text-left text-xs font-medium text-slate-600 hover:border-slate-400 hover:bg-slate-50">{label}</button>)}</div><form className="space-y-4" onSubmit={handleSubmit(onSubmit)}><Field label="Email" error={errors.email?.message}><Input type="email" autoComplete="email" {...register("email")} /></Field><Field label="Password" error={errors.password?.message}><Input type="password" autoComplete="current-password" {...register("password")} /></Field>{serverError && <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{serverError}</p>}<Button className="w-full gap-2" disabled={isSubmitting}>{isSubmitting ? "Signing in…" : "Sign in"}<ArrowRight size={16} /></Button></form></div><p className="mt-5 text-center text-xs leading-5 text-slate-500">Seeded records come from a processed public retail-invoice subset. Dashboard data is loaded from the API.</p></div></section>
  </main>;
}
