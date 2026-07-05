import type { MetadataRoute } from "next";
import { getIndexData, getRunStaticParams } from "@/lib/data";

const SITE_URL = "https://local-bench.ai";
const STATIC_PATHS = ["/", "/leaderboard/", "/compare/", "/methodology/", "/trust/", "/submit/"] as const;

export const dynamic = "force-static";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [index, runParams] = await Promise.all([getIndexData(), getRunStaticParams()]);
  const paths = [
    ...STATIC_PATHS,
    ...index.models.map((model) => `/model/${model.slug}/`),
    ...runParams.map((param) => `/run/${param.runId}/`),
  ];
  return paths.map((path) => ({ url: absoluteUrl(path) }));
}

function absoluteUrl(path: string): string {
  return new URL(path, SITE_URL).toString();
}
