import type { Metadata } from "next";
import { FeedbackForm } from "./feedback-form";
import { pageMetadata } from "@/lib/page-metadata";

export const metadata: Metadata = pageMetadata(
  "Send feedback",
  "Send private product feedback to the local-bench maintainer without creating an account.",
);

export default function FeedbackPage() {
  return <FeedbackForm />;
}
