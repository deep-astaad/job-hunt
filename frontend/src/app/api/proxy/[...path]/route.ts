import { type NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_INTERNAL_URL || "http://django:8000";
const INTERNAL_TOKEN = process.env.INTERNAL_API_TOKEN || "";

type Context = { params: Promise<{ path: string[] }> };

async function handler(req: NextRequest, ctx: Context) {
  const { path } = await ctx.params;
  const apiPath = path.join("/");

  // Reconstruct destination URL (always add trailing slash for Django)
  const dest = new URL(`${BACKEND}/api/${apiPath}/`);

  // Forward all query params
  req.nextUrl.searchParams.forEach((val, key) => dest.searchParams.set(key, val));

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  if (INTERNAL_TOKEN) {
    headers["X-Internal-Token"] = INTERNAL_TOKEN;
  }

  // Forward Django session cookie so staff endpoints work when user is logged in via /admin
  const cookieHeader = req.headers.get("cookie");
  if (cookieHeader) {
    headers["Cookie"] = cookieHeader;
  }

  // For mutation methods forward the X-CSRFToken as well
  const csrf = req.headers.get("x-csrftoken");
  if (csrf) headers["X-CSRFToken"] = csrf;

  let body: string | undefined;
  if (req.method !== "GET" && req.method !== "HEAD") {
    body = await req.text();
  }

  let res: Response;
  try {
    res = await fetch(dest.toString(), {
      method: req.method,
      headers,
      body,
      // Don't follow redirects — let the client handle them
      redirect: "manual",
    });
  } catch (err) {
    console.error("[proxy] fetch error:", err);
    return NextResponse.json({ error: "Backend unreachable" }, { status: 502 });
  }

  const responseBody = await res.text();
  return new NextResponse(responseBody, {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("Content-Type") || "application/json",
    },
  });
}

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const PUT = handler;
export const DELETE = handler;
