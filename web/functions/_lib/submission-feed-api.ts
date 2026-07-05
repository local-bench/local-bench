import type { SubmissionApiEnv } from "./submission-contracts";
import { listAcceptedFeed } from "./submission-store";

export async function handleAcceptedFeed(env: SubmissionApiEnv): Promise<Response> {
  return Response.json(
    { submissions: await listAcceptedFeed(env, 50) },
    { headers: { "cache-control": "public, max-age=300" }, status: 200 },
  );
}
