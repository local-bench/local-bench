import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "local-bench",
  description: "Community quality benchmark leaderboard for local AI setups.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
