export type CurrencyCode = string;
export type MinorUnitAmount = number;
export type TransactionStatus =
  | "created"
  | "pending"
  | "processing"
  | "authorized"
  | "captured"
  | "completed"
  | "partially_refunded"
  | "refunded"
  | "failed"
  | "cancelled"
  | "reversed";

export type ApiErrorEnvelope = {
  error: { code: string; message: string; request_id: string | null };
};
