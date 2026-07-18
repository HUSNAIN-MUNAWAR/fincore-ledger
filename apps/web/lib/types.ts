export type Wallet = {
  id: string; organization_id: string; currency: string; wallet_type: string; status: string;
  available_balance: number; pending_balance: number; reserved_balance: number; ledger_balance: number;
};
export type DashboardSummary = {
  wallet_count: number; available_balance: number; pending_balance: number; reserved_balance: number;
  payment_count: number; payment_volume: number; refund_volume: number; transfer_count: number;
  withdrawal_pending_count: number; currency: string;
};
export type Payment = {
  id: string; reference: string; description: string; amount: number; fee_amount: number; refunded_amount: number;
  currency: string; status: string; created_at: string; customer_wallet_id: string; merchant_wallet_id: string;
};
export type Transfer = {
  id: string; reference: string; description: string; amount: number; fee_amount: number; currency: string;
  status: string; created_at: string; sender_wallet_id: string; receiver_wallet_id: string;
};
export type Withdrawal = {
  id: string; reference: string; amount: number; fee_amount: number; currency: string; status: string;
  destination_masked: string; provider_reference: string | null; review_note: string | null; created_at: string;
};
export type Journal = {
  id: string; reference: string; description: string; currency: string; source_type: string; source_id: string;
  status: string; created_at: string; balanced: boolean;
  postings: { id: string; account_id: string; direction: string; amount: number; memo: string }[];
};
export type ReconciliationRun = {
  id: string; status: string; matched_count: number; mismatch_count: number; started_at: string; completed_at: string | null;
};
export type Webhook = { id: string; url: string; subscribed_events: string[]; enabled: boolean; created_at: string };
export type ApiKey = { id: string; name: string; prefix: string; scopes: string[]; revoked_at: string | null; created_at: string };
