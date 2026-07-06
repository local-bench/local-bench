import type { SubmissionApiEnv } from "./submission-contracts";
import { listAcceptedFeedView } from "./submission-store";

export async function handleAcceptedFeed(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const view = new URL(request.url).searchParams.get("view") === "provisional" ? "provisional" : "verified";
  return Response.json(
    { submissions: await listAcceptedFeedView(env, 50, view) },
    { headers: { "cache-control": "public, max-age=300" }, status: 200 },
  );
}
