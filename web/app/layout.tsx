import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";
import { getIndexData } from "@/lib/data";
import "./globals.css";

export const metadata: Metadata = {
  title: "local-bench",
  description:
    "A community quality leaderboard for local and open LLMs: a modular Local Intelligence Index across agentic, knowledge, instruction, tool-calling, and coding axes.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const index = await getIndexData();
  const usesDemoData = index.models.some((model) => model.demo);

  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <AppShell suiteVersion={index.suite_version} indexVersion={index.index_version} usesDemoData={usesDemoData}>
          {children}
        </AppShell>
      </body>
    </html>
  );
}
