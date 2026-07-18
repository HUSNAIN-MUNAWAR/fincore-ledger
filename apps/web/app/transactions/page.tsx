"use client";

import { AppShell } from "@/components/app-shell";
import { StatusBadge } from "@/components/status-badge";
import { Button, Card, CardHeader, Empty, Field, Input, SecondaryButton, Select } from "@/components/ui";
import { api, idempotencyKey } from "@/lib/api";
import { dateTime, money } from "@/lib/format";
import type { Payment, Transfer, Wallet } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRightLeft, CircleDollarSign, ReceiptText } from "lucide-react";
import { useMemo, useState } from "react";

export default function TransactionsPage() {
  const queryClient = useQueryClient();
  const wallets = useQuery({ queryKey: ["wallets"], queryFn: () => api<Wallet[]>("/wallets") });
  const payments = useQuery({ queryKey: ["payments"], queryFn: () => api<Payment[]>("/payments") });
  const transfers = useQuery({ queryKey: ["transfers"], queryFn: () => api<Transfer[]>("/transfers") });
  const [mode, setMode] = useState<"payment" | "transfer">("payment");
  const [form, setForm] = useState({ destination: "", amount: "", reference: "", description: "" });
  const wallet = wallets.data?.[0];
  const mutation = useMutation({
    mutationFn: async () => {
      if (!wallet) throw new Error("No wallet is available for this organization.");
      const amount = Math.round(Number(form.amount) * 100);
      if (!Number.isInteger(amount) || amount <= 0) throw new Error("Enter a valid positive amount.");
      if (mode === "payment") {
        return api<Payment>("/payments", {
          method: "POST",
          headers: { "Idempotency-Key": idempotencyKey("payment") },
          body: JSON.stringify({ customer_wallet_id: wallet.id, merchant_wallet_id: form.destination, amount, currency: wallet.currency, reference: form.reference, description: form.description, metadata: { channel: "web" }, capture_method: "automatic" }),
        });
      }
      return api<Transfer>("/transfers", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey("transfer") },
        body: JSON.stringify({ sender_wallet_id: wallet.id, receiver_wallet_id: form.destination, amount, currency: wallet.currency, reference: form.reference, description: form.description }),
      });
    },
    onSuccess: async () => {
      setForm({ destination: "", amount: "", reference: "", description: "" });
      await Promise.all([queryClient.invalidateQueries({ queryKey: ["payments"] }), queryClient.invalidateQueries({ queryKey: ["transfers"] }), queryClient.invalidateQueries({ queryKey: ["wallets"] }), queryClient.invalidateQueries({ queryKey: ["summary"] })]);
    },
  });
  const timeline = useMemo(() => [
    ...(payments.data ?? []).map((item) => ({ ...item, type: "payment" as const })),
    ...(transfers.data ?? []).map((item) => ({ ...item, type: "transfer" as const })),
  ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()), [payments.data, transfers.data]);
  return <AppShell title="Transactions" eyebrow="Money movement"><div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]"><Card><CardHeader title="Create transaction" description="The API requires an idempotency key and posts a balanced journal in the same transaction." /><div className="p-5"><div className="mb-5 grid grid-cols-2 rounded-xl bg-slate-100 p-1"><button onClick={() => setMode("payment")} className={`rounded-lg px-3 py-2 text-sm font-semibold ${mode === "payment" ? "bg-white shadow-sm" : "text-slate-500"}`}>Merchant payment</button><button onClick={() => setMode("transfer")} className={`rounded-lg px-3 py-2 text-sm font-semibold ${mode === "transfer" ? "bg-white shadow-sm" : "text-slate-500"}`}>Wallet transfer</button></div><form className="space-y-4" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}><Field label={mode === "payment" ? "Merchant wallet ID" : "Receiver wallet ID"}><Input value={form.destination} onChange={(event) => setForm({ ...form, destination: event.target.value })} placeholder="UUID from the recipient" required /></Field><div className="grid grid-cols-[1fr_120px] gap-3"><Field label="Amount"><Input type="number" min="0.01" step="0.01" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} placeholder="1250.00" required /></Field><Field label="Currency"><Select value={wallet?.currency ?? "PKR"} disabled><option>{wallet?.currency ?? "PKR"}</option></Select></Field></div><Field label="Reference"><Input value={form.reference} onChange={(event) => setForm({ ...form, reference: event.target.value })} placeholder="ORDER-1042" required /></Field><Field label="Description"><Input value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="Invoice or order context" /></Field>{mutation.error && <p className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{mutation.error.message}</p>}{mutation.isSuccess && <p className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-700">Transaction posted successfully.</p>}<Button className="w-full gap-2" disabled={mutation.isPending}>{mode === "payment" ? <CircleDollarSign size={17} /> : <ArrowRightLeft size={17} />}{mutation.isPending ? "Posting…" : mode === "payment" ? "Capture payment" : "Send funds"}</Button></form></div></Card><Card><CardHeader title="Transaction activity" description="Unified view of wallet transfers and merchant payments." action={<SecondaryButton onClick={() => void Promise.all([payments.refetch(), transfers.refetch()])}>Refresh</SecondaryButton>} />{timeline.length ? <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3">Transaction</th><th className="px-5 py-3">Type</th><th className="px-5 py-3">Status</th><th className="px-5 py-3">Amount</th><th className="px-5 py-3">Time</th></tr></thead><tbody>{timeline.map((item) => <tr key={`${item.type}-${item.id}`} className="border-t border-slate-100"><td className="px-5 py-4"><div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-xl bg-slate-100 text-slate-600">{item.type === "payment" ? <ReceiptText size={17} /> : <ArrowRightLeft size={17} />}</span><div><p className="font-medium text-slate-900">{item.reference}</p><p className="mt-0.5 max-w-[230px] truncate text-xs text-slate-500">{item.description || item.id}</p></div></div></td><td className="px-5 py-4 capitalize text-slate-600">{item.type}</td><td className="px-5 py-4"><StatusBadge value={item.status} /></td><td className="px-5 py-4"><p className="font-semibold">{money(item.amount, item.currency)}</p><p className="text-xs text-slate-500">Fee {money(item.fee_amount, item.currency)}</p></td><td className="px-5 py-4 text-slate-500">{dateTime(item.created_at)}</td></tr>)}</tbody></table></div> : <Empty title="No transaction records" detail="Use the form to execute a database-backed payment or transfer." />}</Card></div></AppShell>;
}
