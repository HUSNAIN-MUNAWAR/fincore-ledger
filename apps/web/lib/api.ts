const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

type ApiError = { error?: { code?: string; message?: string } };

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("fincore_access_token");
}

export function setSession(accessToken: string, refreshToken: string, organizationId: string): void {
  window.localStorage.setItem("fincore_access_token", accessToken);
  window.localStorage.setItem("fincore_refresh_token", refreshToken);
  window.localStorage.setItem("fincore_organization_id", organizationId);
}

export function clearSession(): void {
  window.localStorage.removeItem("fincore_access_token");
  window.localStorage.removeItem("fincore_refresh_token");
  window.localStorage.removeItem("fincore_organization_id");
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    let payload: ApiError = {};
    try { payload = await response.json() as ApiError; } catch { /* no body */ }
    throw new Error(payload.error?.message ?? `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function idempotencyKey(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}
