export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const response = await fetch(
      `${process.env.API_INTERNAL_URL || "http://127.0.0.1:8000"}/openapi.json`,
      { cache: "no-store" },
    );
    if (!response.ok)
      return Response.json(
        { detail: "API schema unavailable" },
        { status: 503 },
      );
    const schema = await response.json();
    // Swagger served through /api/docs uses an absolute /openapi.json URL.
    // Keep its interactive requests on the same authenticated API proxy.
    schema.servers = [{ url: "/api", description: "Dashboard API proxy" }];
    return Response.json(schema, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ detail: "API schema unavailable" }, { status: 503 });
  }
}
