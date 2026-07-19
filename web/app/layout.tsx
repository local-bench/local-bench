import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";
import { getIndexData } from "@/lib/data";
import { compareFamilyNames } from "@/lib/family-slug";
import "./globals.css";

const title = "local-bench";
// Season-neutral on purpose: the axis lineup changes per index season, and this string is
// baked into every page's search/social preview.
const description =
  "A community quality leaderboard for local and open LLMs: a modular Local Intelligence Index measured judge-free on real local hardware.";
const siteUrl = "https://local-bench.ai";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title,
  description,
  alternates: { canonical: "./" },
  openGraph: {
    description,
    siteName: "local-bench",
    title,
    type: "website",
    url: `${siteUrl}/`,
  },
  twitter: { card: "summary" },
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const index = await getIndexData();
  const usesDemoData = index.models.some((model) => model.demo);
  const families = [...new Set(index.models.map((model) => model.family))].sort(compareFamilyNames);

  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <AppShell families={families} suiteVersion={index.suite_version} indexVersion={index.index_version} usesDemoData={usesDemoData}>
          {children}
        </AppShell>
      </body>
    </html>
  );
}
