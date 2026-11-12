import { afterEach, describe, expect, it, vi } from "vitest";
import { API_ROOT } from "./api.js";

// Stage 8: API URL configuration tests. Verifies the frontend derives its API
// base URL from the public VITE_API_BASE_URL variable and falls back to /api.
// VITE_* variables are public browser configuration, not secrets.

describe("api.js base URL configuration", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("defaults to /api when VITE_API_BASE_URL is unset", async () => {
    vi.stubEnv("VITE_API_BASE_URL", undefined);
    vi.resetModules();
    const mod = await import("./api.js");
    expect(mod.API_ROOT).toBe("/api");
  });

  it("uses VITE_API_BASE_URL when set", async () => {
    vi.stubEnv(
      "VITE_API_BASE_URL",
      "https://techohub-api.vercel.app/api",
    );
    vi.resetModules();
    const mod = await import("./api.js");
    expect(mod.API_ROOT).toBe("https://techohub-api.vercel.app/api");
  });

  it("strips trailing slashes from VITE_API_BASE_URL", async () => {
    vi.stubEnv(
      "VITE_API_BASE_URL",
      "https://techohub-api.vercel.app/api/",
    );
    vi.resetModules();
    const mod = await import("./api.js");
    expect(mod.API_ROOT).toBe("https://techohub-api.vercel.app/api");
  });

  it("routes API requests through the deployed backend /api prefix", async () => {
    vi.stubEnv(
      "VITE_API_BASE_URL",
      "https://techohub-api.vercel.app/api",
    );
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [],
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.resetModules();
    const mod = await import("./api.js");

    await mod.getServices();

    expect(fetchMock).toHaveBeenCalledWith(
      "https://techohub-api.vercel.app/api/services",
      expect.any(Object),
    );
  });
});
