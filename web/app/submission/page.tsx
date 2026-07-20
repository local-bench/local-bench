import type { Metadata } from "next";
import { pageMetadata } from "@/lib/page-metadata";
import { SubmissionClient } from "./submission-client";

export const metadata: Metadata = pageMetadata(
  "Submission status",
  "Check the validation and publication status of a local-bench result submission by its receipt id.",
);

export default function SubmissionPage() {
  return <SubmissionClient />;
}
