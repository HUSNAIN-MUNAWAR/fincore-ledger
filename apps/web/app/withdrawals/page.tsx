"use client";

import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { Button, Card, CardHeader, Empty, Field, Input, SecondaryButton } from "@/components/ui";
import { api, idempotencyKey } from "@/lib/api";
import { dateTime, money } from "@/lib/format";
import type { Wallet, Withdrawal } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Landmark, XCircle } from "lucide-react";
import { useState } from "react";

export default function WithdrawalsPage() {
  const client = useQueryClient();
  const wallets = useQuery({ queryKey: ["wallets"], queryFn: () => api<Wallet[]>("/wallets") });
  const withdrawals = useQuery({ queryKey: ["withdrawals"], queryFn: () => api<Withdrawal[]>("/withdrawals") });
  const [form, setForm] = useState({ amount: "", destination_masked: "Bank account •••• 8842", reference: "" });
  const create = useMutation({
    mutationFn: () => {
      const wallet = wallets.data?.[0]; if (!wallet) throw new Error("No wallet available.");
      return api<Withdrawal>("/withdrawals", { method: "POST", headers: { "Idempotency-Key": idempotencyKey("withdrawal") }, body: JSON.stringify({ wallet_id: wallet.id, amount: Math.round(Number(form.amount) * 100), currency: wallet.currency, destination_masked: form.destination_masked, reference: form.reference }) });
    },
    onSuccess: async () => { setForm({ amount: "", destination_masked: "Bank account •••• 8842", reference: "" }); await Promise.all([client.invalidateQueries({ queryKey: ["withdrawals"] }), client.invalidateQueries({ queryKey: ["wallets"] })]); },
  });
  const decision = useMutation({ mutationFn: ({ id, action }: { id: string; action: "approve" | "reject" }) => api<Withdrawal>(`/withdrawals/${id}/${action}`, { method: "POST", body: JSON.stringify({ note: action === "approve" ? "Reviewed against configured limits" : "Rejected after operations review" }) }), onSuccess: () => client.invalidateQueries({ queryKey: ["withdrawals"] }) });
  const confirm = useMutation({ mutationFn: (id: string) => api(`/development/withdrawals/${id}/confirm`, { method: "POST" }), onSuccess: async () => { await Promise.all([client.invalidateQueries({ queryKey: ["withdrawals"] }), client.invalidateQueries({ queryKey: ["wallets"] })]); } });
  return <AppShell title="Withdrawals and payouts" eyebrow="Operations queue"><div className="grid gap-6 xl:grid-cols-[0.7fr_1.3fr]"><Card><CardHeader title="Request withdrawal" description="Funds are reserved immediately and remain in the ledger until provider confirmation." /><form className="space-y-4 p-5" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}><Field label="Amount"><Input type="number" min="0.01" step="0.01" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} required /></Field><Field label="Masked destination"><Input value={form.destination_masked} onChange={(event) => setForm({ ...form, destination_masked: event.target.value })} required /></Field><Field label="Reference"><Input value={form.reference} onChange={(event) => setForm({ ...form, reference: event.target.value })} placeholder="PAYOUT-1042" required /></Field>{create.error && <p className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{create.error.message}</p>}<Button className="w-full gap-2" disabled={create.isPending}><Landmark size={17} />{create.isPending ? "Reserving…" : "Submit for review"}</Button></form></Card><Card><CardHeader title="Review queue" description="Operations actions are permission-gated and audit logged." />{withdrawals.data?.length ? <div className="divide-y divide-slate-100">{withdrawals.data.map((item) => <div key={item.id} className="p-5"><div className="flex flex-col justify-between gap-4 md:flex-row md:items-center"><div><div className="flex items-center gap-3"><p className="font-semibold text-slate-900">{item.reference}</p><StatusBadge value={item.status} /></div><p className="mt-2 text-sm text-slate-500">{item.destination_masked} · {dateTime(item.created_at)}</p><p className="mt-1 text-xs text-slate-400">Provider ref: {item.provider_reference ?? "Not submitted"}</p></div><div className="md:text-right"><p className="text-xl font-semibold">{money(item.amount, item.currency)}</p><p className="text-xs text-slate-500">Fee {money(item.fee_amount, item.currency)}</p></div></div>{["requested", "under_review"].includes(item.status) && <div className="mt-4 flex flex-wrap gap-2"><SecondaryButton className="gap-2" onClick={() => decision.mutate({ id: item.id, action: "reject" })}><XCircle size={16} /> Reject</SecondaryButton><Button className="gap-2" onClick={() => decision.mutate({ id: item.id, action: "approve" })}><CheckCircle2 size={16} /> Approve</Button></div>}{item.status === "processing" && <div className="mt-4"><Button onClick={() => confirm.mutate(item.id)}>Confirm test provider completion</Button></div>}{item.review_note && <p className="mt-3 rounded-xl bg-slate-50 p-3 text-sm text-slate-600">Review note: {item.review_note}</p>}</div>)}</div> : <Empty title="No withdrawals" detail="Requested payouts will appear here for review and provider confirmation." />}</Card></div></AppShell>;
}
