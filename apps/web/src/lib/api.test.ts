import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, refreshSession, setAccessToken } from "./api";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const tokens = { access_token: "new-token", token_type: "bearer", expires_in: 900, csrf_token: "c2", user: { id: "u" } };

describe("api client", () => {
  beforeEach(() => {
    setAccessToken("old-token");
    document.cookie = "nexus_csrf=c1; path=/";
  });
  afterEach(() => {
    vi.restoreAllMocks();
    document.cookie = "nexus_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
  });

  it("sends the bearer token", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, { ok: true }));
    await api("/auth/me");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer old-token");
  });

  it("refreshes once on 401 and retries with the new token", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(json(401, { error: { code: "unauthorized", message: "x" } }))
      .mockResolvedValueOnce(json(200, tokens))
      .mockResolvedValueOnce(json(200, { ok: true }));
    await expect(api("/auth/me")).resolves.toEqual({ ok: true });
    const refreshInit = fetchMock.mock.calls[1][1] as RequestInit;
    expect((refreshInit.headers as Record<string, string>)["X-CSRF-Token"]).toBe("c1");
    const retryInit = fetchMock.mock.calls[2][1] as RequestInit;
    expect((retryInit.headers as Record<string, string>).Authorization).toBe("Bearer new-token");
  });

  it("shares one refresh between concurrent callers", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, tokens));
    await Promise.all([refreshSession(), refreshSession(), refreshSession()]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("turns API errors into ApiError with field messages", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json(422, { error: { code: "validation_error", message: "Check the fields.", fields: [{ field: "email", message: "bad" }] } }),
    );
    const err = (await api("/auth/register", { method: "POST", auth: false, body: {} }).catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("validation_error");
    expect(err.fields).toEqual([{ field: "email", message: "bad" }]);
  });

  it("reports network failures clearly", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api("/auth/me")).rejects.toMatchObject({ code: "network_error" });
  });
});
