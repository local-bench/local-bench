import type { Metadata } from "next";
import { FamilyDirectory } from "@/components/family-directory";
import { getIndexData } from "@/lib/data";

export const metadata: Metadata = {
  title: "Model families | local-bench",
  description: "Browse model families, fine-tunes, distills, quants, results, and VRAM on local-bench.",
};

export default async function FamiliesPage() {
  const index = await getIndexData();

  return (
    <main className="mx-auto w-full max-w-[1480px] px-5 py-7 lg:px-8">
      <FamilyDirectory models={index.models} />
    </main>
  );
}
