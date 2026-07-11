import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { existsSync, writeFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { onRequestGet as submissionStatus } from "../functions/api/submissions/[submissionId]";
import { onRequestPost as completeSubmission } from "../functions/api/submissions/[submissionId]/complete";
import { onRequestPost as requestUpload } from "../functions/api/submissions/request-upload";
import { onRequestPost as issueTicket } from "../functions/api/submissions/tickets";
import { sha256Hex } from "./submission-test-support";
import { createEnv } from "./submission-test-support";

const enabled = process.env["B2A_COMPAT_SERVER"] === "1";

/** HTTP bridge used only by scripts/b2a_client_compat_gate.py.
 * Handler logic, D1, PoP, completion, and R2 are real; only the signed Cloudflare R2 URL
 * is adapted to localhost because the test bucket is a Miniflare binding.
 */
describe.runIf(enabled)("B2a N/N-1 Worker compatibility server", () => {
  it("serves the real admission handlers until the compatibility runner finishes", async () => {
    const portFile = requiredEnv("B2A_COMPAT_PORT_FILE");
    const stopFile = requiredEnv("B2A_COMPAT_STOP_FILE");
    const mutateAdmission = process.env["B2A_COMPAT_MUTATE_ADMISSION"] === "1";
    const env = await createEnv({ includeAdminSecret: false, includeR2Secrets: true });
    const server = createServer(async (incoming, outgoing) => {
      try {
        const url = new URL(incoming.url ?? "/", "http://127.0.0.1");
        const bytes = await requestBytes(incoming);
        if (incoming.method === "PUT" && url.pathname.startsWith("/upload/")) {
          await uploadCreateOnly(env, incoming, outgoing, url.pathname.slice("/upload/".length), bytes);
          return;
        }
        const headers = new Headers();
        for (const [key, value] of Object.entries(incoming.headers)) {
          if (typeof value === "string") headers.set(key, value);
        }
        headers.set("cf-connecting-ip", "203.0.113.40");
        let body = bytes.length === 0 ? undefined : bytes;
        if (mutateAdmission && url.pathname === "/api/submissions/tickets" && body !== undefined) {
          const parsed = JSON.parse(Buffer.from(body).toString("utf-8"));
          delete parsed.pop;
          body = Buffer.from(JSON.stringify(parsed));
        }
        const request = new Request(`https://local-bench.ai${url.pathname}${url.search}`, {
          ...(body === undefined ? {} : { body: Buffer.from(body) }), headers, method: incoming.method ?? "GET",
        });
        let response: Response;
        if (incoming.method === "POST" && url.pathname === "/api/submissions/tickets") {
          response = await issueTicket({ env, request });
        } else if (incoming.method === "POST" && url.pathname === "/api/submissions/request-upload") {
          response = await localizeUploadTarget(await requestUpload({ env, request }), server);
        } else {
          const match = /^\/api\/submissions\/([^/]+)(\/complete)?$/.exec(url.pathname);
          if (match === null) {
            response = new Response(JSON.stringify({ code: "not_found" }), { status: 404 });
          } else if (incoming.method === "POST" && match[2] === "/complete") {
            response = await completeSubmission({ env, params: { submissionId: match[1]! }, request });
          } else if (incoming.method === "GET" && match[2] === undefined) {
            response = await submissionStatus({ env, params: { submissionId: match[1]! } });
          } else {
            response = new Response(JSON.stringify({ code: "method_not_allowed" }), { status: 405 });
          }
        }
        await sendResponse(outgoing, response);
      } catch (error) {
        outgoing.writeHead(500, { "content-type": "application/json" }).end(JSON.stringify({ error: String(error) }));
      }
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    if (address === null || typeof address === "string") throw new Error("compat server did not bind TCP");
    writeFileSync(portFile, String(address.port));
    try {
      const deadline = Date.now() + 10 * 60 * 1000;
      while (!existsSync(stopFile) && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      expect(existsSync(stopFile)).toBe(true);
    } finally {
      await new Promise<void>((resolve, reject) => server.close((error) => error === undefined ? resolve() : reject(error)));
    }
  }, 11 * 60 * 1000);
});

async function localizeUploadTarget(response: Response, server: ReturnType<typeof createServer>): Promise<Response> {
  if (!response.ok) return response;
  const body = await response.json() as Record<string, unknown>;
  const address = server.address();
  if (address === null || typeof address === "string") throw new Error("compat server has no TCP address");
  body["upload_url"] = `http://127.0.0.1:${address.port}/upload/${body["content_sha256"]}`;
  return new Response(JSON.stringify(body), { headers: { "content-type": "application/json" }, status: response.status });
}

async function uploadCreateOnly(
  env: Awaited<ReturnType<typeof createEnv>>,
  request: IncomingMessage,
  response: ServerResponse,
  declaredSha: string,
  bytes: Uint8Array,
): Promise<void> {
  const key = `submissions/raw/${declaredSha}.json`;
  if (request.headers["if-none-match"] !== "*" || await sha256Hex(Buffer.from(bytes).toString("utf-8")) !== declaredSha || await env.SUBMISSIONS.get(key) !== null) {
    response.writeHead(412, { "content-type": "application/json" }).end(JSON.stringify({ code: "create_only_failed" }));
    return;
  }
  await env.SUBMISSIONS.put(key, bytes, { onlyIf: { etagDoesNotMatch: "*" } });
  response.writeHead(200).end();
}

async function requestBytes(request: IncomingMessage): Promise<Uint8Array> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  return Buffer.concat(chunks);
}

async function sendResponse(target: ServerResponse, response: Response): Promise<void> {
  const headers = Object.fromEntries(response.headers.entries());
  target.writeHead(response.status, headers).end(Buffer.from(await response.arrayBuffer()));
}

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (value === undefined || value.length === 0) throw new Error(`${name} is required`);
  return value;
}
