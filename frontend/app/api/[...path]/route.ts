// Stream API traffic without logging URLs, credentials, bodies or source text.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ path: string[] }> };

async function forward(request: Request, context: Context) {
  const requestId = crypto.randomUUID();
  const deadline = AbortSignal.timeout(110_000);
  const safeHeaders = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Request-ID": requestId,
  };
  try {
    const { path } = await context.params;
    const upload = request.method === "POST" && path.at(-1) === "documents";
    const declared = request.headers.get("content-length");
    const length = declared === null ? 0 : Number(declared);
    const maximum = upload ? 21 * 1024 * 1024 : 256 * 1024;
    if (!Number.isSafeInteger(length) || length < 0 || length > maximum) {
      return Response.json(
        { detail: "Request body exceeds the size limit" },
        { status: 413, headers: safeHeaders },
      );
    }
    if (upload && declared === null) {
      return Response.json(
        { detail: "Content-Length is required for uploads" },
        { status: 411, headers: safeHeaders },
      );
    }
    if (
      path.some((part) => part === "." || part === ".." || /[\\\0]/.test(part))
    ) {
      return Response.json(
        { detail: "Invalid API path" },
        { status: 400, headers: safeHeaders },
      );
    }
    const base = new URL(
      (process.env.API_INTERNAL_URL || "http://127.0.0.1:8000").replace(
        /\/+$/,
        "",
      ) + "/",
    );
    const target = new URL(path.map(encodeURIComponent).join("/"), base);
    target.search = new URL(request.url).search;
    const headers = new Headers({ "Accept-Encoding": "identity" });
    for (const name of [
      "accept",
      "authorization",
      "content-type",
      "content-length",
      "cookie",
      "origin",
      "access-control-request-method",
      "access-control-request-headers",
    ]) {
      const value = request.headers.get(name);
      if (value !== null) headers.set(name, value);
    }
    const body =
      request.method === "GET" || request.method === "HEAD"
        ? undefined
        : request.body;
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      ...(body ? { duplex: "half" as const } : {}),
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.any([request.signal, deadline]),
    });
    const responseHeaders = new Headers();
    for (const [name, value] of upstream.headers) {
      if (
        ![
          "connection",
          "keep-alive",
          "transfer-encoding",
          "set-cookie",
        ].includes(name.toLowerCase())
      )
        responseHeaders.set(name, value);
    }
    for (const cookie of upstream.headers.getSetCookie())
      responseHeaders.append("Set-Cookie", cookie);
    const location = responseHeaders.get("location");
    if (location) {
      const redirect = new URL(location, target);
      if (redirect.origin === base.origin)
        responseHeaders.set(
          "location",
          "/api" + redirect.pathname + redirect.search + redirect.hash,
        );
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    // Do not retry mutations: the backend may have committed before disconnect.
    console.warn(
      JSON.stringify({
        event: "api_upstream_unavailable",
        request_id: requestId,
        timeout: deadline.aborted,
      }),
    );
    return Response.json(
      {
        detail: deadline.aborted
          ? "The API request timed out. Check status before retrying."
          : "The API is temporarily unavailable. Check status before retrying.",
        request_id: requestId,
      },
      { status: deadline.aborted ? 504 : 503, headers: safeHeaders },
    );
  }
}

export {
  forward as GET,
  forward as HEAD,
  forward as POST,
  forward as PUT,
  forward as PATCH,
  forward as DELETE,
  forward as OPTIONS,
};
