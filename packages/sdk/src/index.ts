import { createHmac, timingSafeEqual } from "node:crypto";

export type FinCoreClientOptions = {
  apiKey: string;
  baseUrl?: string;
};

export type PaymentCreate = {
  customer_wallet_id: string;
  merchant_wallet_id: string;
  amount: number;
  currency: string;
  reference: string;
  description?: string;
  metadata?: Record<string, unknown>;
  capture_method?: "automatic" | "manual";
};

export type Payment = PaymentCreate & {
  id: string;
  fee_amount: number;
  refunded_amount: number;
  status: string;
  created_at: string;
};

export class FinCoreClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;

  constructor(options: FinCoreClientOptions) {
    if (!options.apiKey) throw new Error("apiKey is required");
    this.apiKey = options.apiKey;
    this.baseUrl = (options.baseUrl ?? "http://localhost:8000/api/v1").replace(/\/$/, "");
  }

  readonly payments = {
    create: async (payload: PaymentCreate, idempotencyKey: string): Promise<Payment> =>
      this.request<Payment>("/payments", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      }),
    retrieve: async (paymentId: string): Promise<Payment> =>
      this.request<Payment>(`/payments/${paymentId}`),
    list: async (): Promise<Payment[]> => this.request<Payment[]>("/payments"),
    refund: async (
      paymentId: string,
      payload: { amount: number; reason: string },
      idempotencyKey: string,
    ): Promise<Record<string, unknown>> =>
      this.request(`/payments/${paymentId}/refunds`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(payload),
      }),
  };

  async listWallets(): Promise<Record<string, unknown>[]> {
    return this.request<Record<string, unknown>[]>("/wallets");
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": this.apiKey,
        ...init.headers,
      },
    });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(`FinCore API ${response.status}: ${body}`);
    }
    return response.json() as Promise<T>;
  }
}

export function verifyWebhookSignature(params: {
  secret: string;
  timestamp: number;
  payload: string;
  signature: string;
  toleranceSeconds?: number;
}): boolean {
  const tolerance = params.toleranceSeconds ?? 300;
  const age = Math.abs(Math.floor(Date.now() / 1000) - params.timestamp);
  if (age > tolerance) return false;
  const expected = createHmac("sha256", params.secret)
    .update(`${params.timestamp}.${params.payload}`)
    .digest("hex");
  const left = Buffer.from(expected, "hex");
  const right = Buffer.from(params.signature, "hex");
  return left.length === right.length && timingSafeEqual(left, right);
}
