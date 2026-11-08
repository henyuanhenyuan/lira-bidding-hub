export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    if (window.location.pathname !== "/next/login") {
      window.location.replace("/next/login");
    }
    throw new ApiError(401, "未登录");
  }
  if (!res.ok) {
    let message = res.statusText || `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) message = body.detail;
    } catch {
      /* 非 JSON 错误体 */
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return null as T;
  return (await res.json()) as T;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export const api = {
  get<T>(path: string): Promise<T> {
    return fetch(path).then((res) => handle<T>(res));
  },
  post<T>(path: string, body?: unknown): Promise<T> {
    return fetch(path, {
      method: "POST",
      headers: JSON_HEADERS,
      body: body === undefined ? "{}" : JSON.stringify(body),
    }).then((res) => handle<T>(res));
  },
  patch<T>(path: string, body: unknown): Promise<T> {
    return fetch(path, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }).then((res) => handle<T>(res));
  },
};

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
