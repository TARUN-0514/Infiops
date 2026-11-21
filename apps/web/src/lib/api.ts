import type { TokenResponse } from "./types";

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly fields: { field: string; message: string }[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// The access token lives only in memory. The refresh token is an httpOnly cookie the page cannot read.
let accessToken: string | null = null;
let refreshing: Promise<TokenResponse | null> | null = null;
const listeners = new Set<(t: TokenResponse | null) => void>();

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function onSessionChange(fn: (t: TokenResponse | null) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    const e = body?.error ?? {};
    return new ApiError(res.status, e.code ?? "error", e.message ?? "Something went wrong.", e.fields ?? []);
  } catch {
    return new ApiError(res.status, "error", "Something went wrong. Try again.");
  }
}

/** Exchange the refresh cookie for a new access token. Concurrent callers share one request. */
export function refreshSession(): Promise<TokenResponse | null> {
  if (!refreshing) {
    refreshing = (async () => {
      const csrf = readCookie("nexus_csrf");
      if (!csrf) return null;
      try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRF-Token": csrf },
        });
        if (!res.ok) return null;
        return (await res.json()) as TokenResponse;
      } catch {
        return null;
      }
    })().then((tokens) => {
      setAccessToken(tokens?.access_token ?? null);
      listeners.forEach((fn) => fn(tokens));
      return tokens;
    });
    void refreshing.finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

type Options = { method?: string; body?: unknown; auth?: boolean };

export async function api<T>(path: string, { method = "GET", body, auth = true }: Options = {}): Promise<T> {
  const send = () => {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`;
    return fetch(`${API_BASE}${path}`, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  };

  let res: Response;
  try {
    res = await send();
    if (res.status === 401 && auth) {
      const tokens = await refreshSession();
      if (tokens) res = await send();
    }
  } catch {
    throw new ApiError(0, "network_error", "Can't reach NEXUS. Check your connection.");
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
