type PrivateGateEnv = {
  readonly LOCALBENCH_PRIVATE_BYPASS_TOKEN?: string;
  readonly LOCALBENCH_SITE_PRIVATE?: string;
};

type PrivateGateContext = {
  readonly env: PrivateGateEnv;
  readonly next: () => Promise<Response>;
  readonly request: Request;
};

const BYPASS_COOKIE_NAME = "lb_private_bypass";
const BYPASS_HEADER_NAME = "x-localbench-bypass";
const PRIVATE_MODE_VALUES = new Set(["1", "true", "yes", "on"]);

export async function onRequest(context: PrivateGateContext): Promise<Response> {
  if (!isPrivateModeEnabled(context.env)) {
    return context.next();
  }

  const requestUrl = new URL(context.request.url);
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
