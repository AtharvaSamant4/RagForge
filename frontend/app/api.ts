export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch("/api" + path, {
    credentials: "same-origin",
    ...init,
    headers: {
      ...(init.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...init.headers,
    },
  });
  if (!response.ok) {
    if (
      response.status === 401 &&
      !path.startsWith("/v1/auth/") &&
      typeof window !== "undefined"
    )
      window.dispatchEvent(new Event("ragforge-session-expired"));
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : body.detail?.message
          ? body.detail.message
          : Array.isArray(body.detail)
            ? body.detail.map((x: { msg: string }) => x.msg).join("; ")
            : `Request failed (${response.status})`,
    );
  }
  return response.json();
}
export function download(data: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
