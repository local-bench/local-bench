type ArtifactR2Range = {
  readonly length: number;
  readonly offset: number;
};

type ArtifactR2RangeRequest =
  | { readonly length?: number; readonly offset: number }
  | { readonly suffix: number };

type ArtifactR2ObjectBody = {
  readonly body: ReadableStream<Uint8Array>;
  readonly httpEtag: string;
  readonly httpMetadata: { readonly contentType?: string };
  readonly range: ArtifactR2Range;
  readonly size: number;
};

type ArtifactR2Bucket = {
  get(
    key: string,
    options?: { readonly range: ArtifactR2RangeRequest },
  ): Promise<ArtifactR2ObjectBody | null>;
};

export type ArtifactEnv = {
  readonly ARTIFACTS: ArtifactR2Bucket;
};

type ArtifactRouteParams = {
  readonly path?: string | readonly string[];
};

type ArtifactContext = {
  readonly env: ArtifactEnv;
  readonly params: ArtifactRouteParams;
  readonly request: Request;
};

const ARTIFACT_KEY_PATTERN = /^artifacts\/agentic\/[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/;
const IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable";

export async function onRequest(context: ArtifactContext): Promise<Response> {
  if (context.request.method !== "GET" && context.request.method !== "HEAD") {
    return Response.json(
      { error: "method_not_allowed" },
      { headers: { allow: "GET, HEAD" }, status: 405 },
    );
  }

  const key = artifactKey(context.params.path);
  if (key === null) {
    return notFound();
  }

  const requestedRange = parseRangeHeader(context.request.headers.get("range"));
  if (requestedRange === "invalid") {
    return Response.json({ error: "invalid_range" }, { status: 416 });
  }
  const rangeOptions = requestedRange === null ? undefined : { range: requestedRange };
  const object = await context.env.ARTIFACTS.get(key, rangeOptions);
  if (object === null) {
    return notFound();
  }

  const headers = new Headers({
    "accept-ranges": "bytes",
    "cache-control": IMMUTABLE_CACHE_CONTROL,
    "content-length": String(requestedRange === null ? object.size : object.range.length),
    "content-type": object.httpMetadata.contentType ?? "application/octet-stream",
    etag: object.httpEtag,
  });
  if (requestedRange !== null) {
    const lastByte = object.range.offset + object.range.length - 1;
    headers.set("content-range", `bytes ${object.range.offset}-${lastByte}/${object.size}`);
  }

  return new Response(context.request.method === "HEAD" ? null : object.body, {
    headers,
    status: requestedRange === null ? 200 : 206,
  });
}

function artifactKey(path: ArtifactRouteParams["path"]): string | null {
  const segments = typeof path === "string" ? path.split("/") : path;
  if (segments === undefined || segments.length === 0 || segments.some((segment) => segment.length === 0 || segment === "..")) {
    return null;
  }
  const key = `artifacts/${segments.join("/")}`;
  return ARTIFACT_KEY_PATTERN.test(key) ? key : null;
}

function parseRangeHeader(header: string | null): ArtifactR2RangeRequest | "invalid" | null {
  if (header === null) {
    return null;
  }
  const match = /^bytes=(\d*)-(\d*)$/.exec(header);
  const startText = match?.[1];
  const endText = match?.[2];
  if (startText === undefined || endText === undefined || (startText.length === 0 && endText.length === 0)) {
    return "invalid";
  }
  if (startText.length === 0) {
    const suffix = Number(endText);
    return Number.isSafeInteger(suffix) && suffix > 0 ? { suffix } : "invalid";
  }
  const offset = Number(startText);
  if (!Number.isSafeInteger(offset)) {
    return "invalid";
  }
  if (endText.length === 0) {
    return { offset };
  }
  const end = Number(endText);
  return Number.isSafeInteger(end) && end >= offset
    ? { length: end - offset + 1, offset }
    : "invalid";
}

function notFound(): Response {
  return Response.json({ error: "not_found" }, { status: 404 });
}
