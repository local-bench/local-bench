import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SubmissionsTable } from "../components/submissions-lifecycle";
import SubmissionPage, { SubmissionDetails } from "../app/submission/page";
import SubmissionsPage from "../app/submissions/page";
import type { CommunityBoardRow } from "../lib/community-data";
import {
  mergeSubmissionLifecycleRows,
  parseSubmissionLifecyclePage,
  reasonCodeLabel,
} from "../lib/submission-lifecycle";

const PUBLISHED_ID = `ticket_${"1".repeat(32)}`;
const REJECTED_ID = `ticket_${"2".repeat(32)}`;
const HELD_ID = `ticket_${"3".repeat(32)}`;

const payload = {
  next_cursor: "cursor-2",
  submissions: [
    lifecycleRow(PUBLISHED_ID, { publish_state: "published", status: "accepted" }),
    lifecycleRow(REJECTED_ID, { reason_code: "metadata_unsafe", status: "rejected" }),
    lifecycleRow(HELD_ID, { held_for_review: true, status: "accepted" }),
  ],
};

function lifecycleRow(submissionId: string, overrides: Record<string, unknown>) {
  return {
    created_at: "2026-07-18T01:00:00Z",
    declared_model_slug: "fixture-model",
    held_for_review: false,
    published_at: null,
    publish_state: "hidden",
    status: "pending_verification",
    submission_id: submissionId,
    submitter_display_name: "Ada",
    github_login: "octocat",
    validated_at: "2026-07-18T02:00:00Z",
    ...overrides,
  };
}

const publishedCommunityRow: CommunityBoardRow = {
  artifactSha256: "a".repeat(64),
  compositeFull: 0.5,
  detailPath: "/model/fixture-model",
  displayName: "Published model",
  family: "Fixture",
  globalRank: 1,
  headlineComplete: true,
  identityLabel: "community-declared, identity-unverified",
  indexVersion: "index-v4.1",
  lineage: undefined,
  measuredHeadlineWeight: 1,
  missingHeadlineWeight: 0,
  partialComposite: 0.5,
  quantLabel: "Q4_K_M",
  ranked: false,
  submissionId: PUBLISHED_ID,
  submitterKeyFingerprint: "abcdef123456",
  trust: {
    agentic_provenance: "self_reported",
    coding_state: "pending",
    replicated: false,
    tier: "re-scored",
    trust_label: "community_re_scored",
    verification_level: "bundle_rescored",
  },
};

describe("public submissions lifecycle", () => {
  it("server-renders the lifecycle legend, checker, and JavaScript-off guidance", () => {
    const html = renderToStaticMarkup(<SubmissionsPage />);

    expect(html).toContain("received → validated → published → review-hold → rejected");
    expect(html).toContain('href="/submission"');
    expect(html).toContain("Check a submission");
    expect(html).toContain("<noscript>");
    expect(html).toContain("JavaScript is off");
  });

  it("links the submission checker back to the lifecycle board", () => {
    const html = renderToStaticMarkup(<SubmissionPage />);

    expect(html).toContain('href="/submissions"');
    expect(html).toContain("View all submissions");
  });

  it("parses one bounded page and merges live publication evidence", () => {
    const parsed = parseSubmissionLifecyclePage(payload);
    if (parsed === null) throw new Error("lifecycle fixture must parse");

    const rows = mergeSubmissionLifecycleRows(parsed.submissions, [publishedCommunityRow]);

    expect(parsed.nextCursor).toBe("cursor-2");
    expect(rows).toMatchObject([
      { communityDetailPath: "/model/fixture-model", stateLabel: "Published" },
      { reasonLabel: "Unsafe metadata", stateLabel: "Rejected" },
      { stateLabel: "Accepted" },
    ]);
  });

  it("rejects oversized, bidi, and unknown lifecycle fields", () => {
    const oversized = { ...payload, submissions: [lifecycleRow(PUBLISHED_ID, { declared_model_slug: "x".repeat(141) })] };
    const bidi = { ...payload, submissions: [lifecycleRow(PUBLISHED_ID, { submitter_display_name: "Ada\u202e" })] };

    expect(parseSubmissionLifecyclePage(oversized)).toBeNull();
    expect(parseSubmissionLifecyclePage(bidi)).toBeNull();
    expect(parseSubmissionLifecyclePage({ ...payload, unexpected: true })).toBeNull();
  });

  it("humanizes known reason codes and passes through bounded unknown codes", () => {
    expect(reasonCodeLabel("metadata_unsafe")).toBe("Unsafe metadata");
    expect(reasonCodeLabel("future_code")).toBe("future_code");
  });

  it("renders lifecycle links and an explicit load-more control", () => {
    const parsed = parseSubmissionLifecyclePage(payload);
    if (parsed === null) throw new Error("lifecycle fixture must parse");
    const rows = mergeSubmissionLifecycleRows(parsed.submissions, [publishedCommunityRow]);
    const html = renderToStaticMarkup(
      <SubmissionsTable loadingMore={false} nextCursor={parsed.nextCursor} onLoadMore={() => undefined} rows={rows} />,
    );

    expect(html).toContain(`/submission?id=${PUBLISHED_ID}`);
    expect(html).toContain("/model/fixture-model");
    expect(html).toContain("Load more");
    expect(html).not.toContain("Held for review");
    expect(html).toContain("Unsafe metadata");
    expect(html).toContain("submitted as Ada — unverified");
    expect(html).not.toContain('href="https://github.com/');
  });

  it("renders bounded rejection reasons and plain submitter detail", () => {
    const rejected = renderToStaticMarkup(<SubmissionDetails value={{
      publish_state: "hidden",
      raw_bundle_sha256: "a".repeat(64),
      reason_code: "metadata_unsafe",
      status: "rejected",
      submission_id: REJECTED_ID,
    }} />);
    const published = renderToStaticMarkup(<SubmissionDetails value={{
      publish_state: "published",
      raw_bundle_sha256: "b".repeat(64),
      status: "accepted",
      submission_id: PUBLISHED_ID,
      submitter_display_name: "Ada",
      trust_label: "community_re_scored",
    }} />);

    expect(rejected).toContain("Unsafe metadata");
    expect(published).toContain("submitted as Ada — unverified");
    expect(published).not.toContain("re-scored");
  });
});
