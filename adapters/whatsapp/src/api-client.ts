/**
 * Client HTTP pour communiquer avec l'API leRH (Python/FastAPI).
 *
 * Toutes les requêtes sont routées vers l'API Python qui contient
 * la logique métier (assistants IA, profiling, matching, etc.).
 */

const BASE_URL = process.env.LERH_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiRequest<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "User-Agent": "leRH-WhatsApp/0.1.0",
    "X-API-Key": process.env.INTERNAL_API_KEY || "",
    ...(options.headers as Record<string, string>),
  };

  if (!headers["X-API-Key"]) {
    console.warn(`[API Client] Missing X-API-Key for request to ${url}`);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);

  try {
    const res = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new ApiError(res.status, `API ${res.status}: ${body}`);
    }

    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if ((err as Error).name === "AbortError") {
      throw new ApiError(408, "API timeout after 30s");
    }
    throw new ApiError(502, `API unreachable: ${(err as Error).message}`);
  } finally {
    clearTimeout(timeout);
  }
}
