import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { AppShell } from "@/components/app-shell";
import { getIndexData } from "@/lib/data";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "local-bench",
  description:
    "A community quality leaderboard for local and open LLMs — Local Intelligence Index (Knowledge + Instruction), measured on a frozen, reproducible suite and anchored against frontier models.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const index = await getIndexData();
  const usesDemoData = index.models.some((model) => model.demo);

  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="font-sans antialiased">
        <AppShell suiteVersion={index.suite_version} indexVersion={index.index_version} usesDemoData={usesDemoData}>
          {children}
        </AppShell>
      </body>
    </html>
  );
}
