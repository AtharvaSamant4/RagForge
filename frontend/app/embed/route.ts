export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  const url = new URL(request.url),
    project = url.searchParams.get("project");
  if (!project || project.length > 40)
    return new Response("Invalid assistant link", { status: 400 });
  try {
    const response = await fetch(
      `${process.env.API_INTERNAL_URL || "http://127.0.0.1:8000"}/v1/public/${encodeURIComponent(project)}/frame-policy`,
      { cache: "no-store" },
    );
    if (!response.ok)
      return new Response("Assistant unavailable or access revoked", {
        status: response.status,
      });
    const config = await response.json();
    const safe = JSON.stringify({ project }).replaceAll("<", "\\u003c");
    const ancestors = (config.allowed_origins as string[]).join(" ");
    return new Response(
      `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Knowledge assistant</title><link rel="stylesheet" href="/embed.css"></head><body><header><span id="title"></span><small>Grounded in source documents</small></header><main id="messages" aria-live="polite"></main><form id="form"><label for="question">Ask a question</label><div><input id="question" maxlength="2000" minlength="2" required autocomplete="off" placeholder="What would you like to know?"><button id="send">Send</button></div></form><footer>Public knowledge assistant · Verify cited sources</footer><script type="application/json" id="config">${safe}</script><script src="/embed-client.js" defer></script></body></html>`,
      {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "no-store",
          "Referrer-Policy": "no-referrer",
          "Content-Security-Policy": `default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors ${ancestors || "'none'"}; base-uri 'none'; form-action 'none'`,
          "X-Content-Type-Options": "nosniff",
        },
      },
    );
  } catch {
    return new Response("Assistant service unavailable", { status: 503 });
  }
}
