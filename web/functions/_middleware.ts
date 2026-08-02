import { MAINTENANCE_MODE } from "../lib/maintenance-mode";

type PrivateGateEnv = {
  readonly LOCALBENCH_PRIVATE_BYPASS_TOKEN?: string;
  readonly LOCALBENCH_SITE_PRIVATE?: string;
  readonly MAINTENANCE_MODE?: string;
};

type PrivateGateContext = {
  readonly env: PrivateGateEnv;
  readonly next: () => Promise<Response>;
  readonly request: Request;
};

const BYPASS_COOKIE_NAME = "lb_private_bypass";
const BYPASS_HEADER_NAME = "x-localbench-bypass";
const MAINTENANCE_MESSAGE =
  "local-bench is being rebuilt around a new, much faster methodology. Every previously published result is preserved and will return with the new site.";
const PRIVATE_MODE_VALUES = new Set(["1", "true", "yes", "on"]);

export async function onRequest(context: PrivateGateContext): Promise<Response> {
  const requestUrl = new URL(context.request.url);
  // public/_routes.json includes /* with no exclusions, so Pages invokes this root middleware before serving static assets.
  if (isMaintenanceModeEnabled(context.env)) {
    return maintenanceResponse(requestUrl.pathname);
  }
  if (requestUrl.pathname.startsWith("/artifacts/")) {
    return context.next();
  }
  if (!isPrivateModeEnabled(context.env)) {
    return context.next();
  }

  const bypassToken = context.env.LOCALBENCH_PRIVATE_BYPASS_TOKEN;
  if (bypassToken !== undefined && bypassToken.length > 0) {
    const queryToken = requestUrl.searchParams.get("lb_bypass");
    if (queryToken === bypassToken) {
      return withBypassCookie(await context.next(), bypassToken);
    }
    if (requestHasBypass(context.request, bypassToken)) {
      return context.next();
    }
  }

  return privateModeResponse();
}

function isMaintenanceModeEnabled(env: PrivateGateEnv): boolean {
  return MAINTENANCE_MODE || env.MAINTENANCE_MODE?.trim() === "1";
}

function maintenanceResponse(pathname: string): Response {
  const headers = {
    "cache-control": "no-store",
    "retry-after": "86400",
    "x-robots-tag": "noindex",
  } as const;
  if (pathname === "/api" || pathname.startsWith("/api/") || pathname.endsWith(".json")) {
    return Response.json({ status: "maintenance", message: MAINTENANCE_MESSAGE }, { headers, status: 503 });
  }
  return new Response(maintenancePage(), {
    headers: { ...headers, "content-type": "text/html; charset=utf-8" },
    status: 503,
  });
}

function maintenancePage(): string {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>local-bench</title>
  <style>
    :root { color-scheme: dark; }
    * { box-sizing: border-box; }
    body {
      min-height: 100vh;
      margin: 0;
      display: grid;
      place-items: center;
      background: #090b0d;
      color: #f2f3f4;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main { width: min(42rem, calc(100% - 3rem)); padding: 4rem 0; }
    h1 { margin: 0 0 1.25rem; font-size: clamp(2.5rem, 9vw, 5rem); line-height: 0.95; letter-spacing: -0.055em; }
    p { margin: 0; max-width: 38rem; color: #b8bdc3; font-size: clamp(1rem, 2.5vw, 1.2rem); line-height: 1.65; }
    footer { margin-top: 3rem; color: #7f868e; font-size: 0.9rem; }
  </style>
</head>
<body>
  <main>
    <h1>Being rebuilt</h1>
    <p>${MAINTENANCE_MESSAGE}</p>
    <footer>— the maintainer</footer>
  </main>
</body>
</html>`;
}

function isPrivateModeEnabled(env: PrivateGateEnv): boolean {
  return PRIVATE_MODE_VALUES.has((env.LOCALBENCH_SITE_PRIVATE ?? "").trim().toLowerCase());
}

function requestHasBypass(request: Request, bypassToken: string): boolean {
  return request.headers.get(BYPASS_HEADER_NAME) === bypassToken || cookieValue(request, BYPASS_COOKIE_NAME) === bypassToken;
}

function cookieValue(request: Request, name: string): string | null {
  const cookieHeader = request.headers.get("cookie");
  if (cookieHeader === null) {
    return null;
  }
  for (const part of cookieHeader.split(";")) {
    const [rawName, ...rawValue] = part.trim().split("=");
    if (rawName === name) {
      return decodeURIComponent(rawValue.join("="));
    }
  }
  return null;
}

function withBypassCookie(response: Response, bypassToken: string): Response {
  const headers = new Headers(response.headers);
  headers.append("set-cookie", `${BYPASS_COOKIE_NAME}=${encodeURIComponent(bypassToken)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=86400`);
  return new Response(response.body, {
    headers,
    status: response.status,
    statusText: response.statusText,
  });
}

function privateModeResponse(): Response {
  return new Response("local-bench is temporarily private.\n", {
    headers: {
      "cache-control": "no-store",
      "content-type": "text/plain; charset=utf-8",
      "x-robots-tag": "noindex",
    },
    status: 503,
  });
}
