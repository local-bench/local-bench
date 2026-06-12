import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import path from "node:path";

const root = path.resolve(process.argv[2] ?? "out");
const port = Number.parseInt(process.argv[3] ?? "4321", 10);

if (!Number.isInteger(port) || port <= 0) {
  throw new Error(`Invalid port: ${process.argv[3] ?? ""}`);
}

const MIME_TYPES = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".map", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml; charset=utf-8"],
  [".txt", "text/plain; charset=utf-8"],
  [".webp", "image/webp"],
]);

const server = createServer(async (request, response) => {
  try {
    await handleRequest(request, response);
  } catch (error) {
    console.error(error);
    response.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    response.end("Internal Server Error");
  }
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Serving ${root} at http://127.0.0.1:${port}`);
});

async function handleRequest(request, response) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    response.writeHead(405, { "content-type": "text/plain; charset=utf-8" });
    response.end("Method Not Allowed");
    return;
  }

  const urlPath = parseUrlPath(request.url ?? "/");
  const filePath = await findFilePath(urlPath);

  if (filePath === null) {
    const notFoundPath = await resolveCandidate("/404.html");
    if (notFoundPath === null) {
      response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      response.end("Not Found");
      return;
    }
    await sendFile(request, response, notFoundPath, 404);
    return;
  }

  await sendFile(request, response, filePath, 200);
}

function parseUrlPath(rawUrl) {
  const parsed = new URL(rawUrl, "http://127.0.0.1");
  return decodeURIComponent(parsed.pathname);
}

async function findFilePath(urlPath) {
  for (const candidate of getCandidates(urlPath)) {
    const filePath = await resolveCandidate(candidate);
    if (filePath !== null) {
      return filePath;
    }
  }
  return null;
}

function getCandidates(urlPath) {
  const candidates = urlPath.endsWith("/")
    ? [`${urlPath}index.html`]
    : [urlPath, `${urlPath}.html`, `${urlPath}/index.html`];
  return [...candidates, ...getNextRscCandidates(urlPath)];
}

function getNextRscCandidates(urlPath) {
  const baseName = path.posix.basename(urlPath);
  if (!baseName.startsWith("__next.") || !baseName.endsWith(".txt")) {
    return [];
  }

  const stem = baseName.slice(0, -".txt".length);
  const parts = stem.split(".");
  if (parts.length < 3) {
    return [];
  }

  const routeSegment = `${parts[0]}.${parts[1]}`;
  const rest = parts.slice(2);
  const last = rest[rest.length - 1];
  if (last === undefined) {
    return [];
  }

  return [path.posix.join(path.posix.dirname(urlPath), routeSegment, ...rest.slice(0, -1), `${last}.txt`)];
}

async function resolveCandidate(urlPath) {
  const relativePath = urlPath.replace(/^\/+/, "");
  const filePath = path.resolve(root, relativePath);
  if (!isInsideRoot(filePath)) {
    return null;
  }

  const fileStat = await stat(filePath).catch(() => null);
  return fileStat?.isFile() === true ? filePath : null;
}

function isInsideRoot(filePath) {
  const relative = path.relative(root, filePath);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

async function sendFile(request, response, filePath, statusCode) {
  const fileStat = await stat(filePath);
  const contentType = MIME_TYPES.get(path.extname(filePath)) ?? "application/octet-stream";
  response.writeHead(statusCode, {
    "cache-control": "no-store",
    "content-length": fileStat.size,
    "content-type": contentType,
  });

  if (request.method === "HEAD") {
    response.end();
    return;
  }

  createReadStream(filePath).pipe(response);
}
