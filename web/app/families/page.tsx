import type { Metadata } from "next";
import { FamilyDirectory } from "@/components/family-directory";
import { getCommunityBoardRows } from "@/lib/community-data";
import { communityRowsWithFamilyPaths } from "@/lib/community-family";
import { getIndexData, getIndexModelsWithArtifacts } from "@/lib/data";
import { familyResolutionContext } from "@/lib/family-resolution-data";

export const metadata: Metadata = {
  title: "Model families | local-bench",
  description: "Browse model families, fine-tunes, distills, quants, results, and VRAM on local-bench.",
};

export default async function FamiliesPage() {
  const index = await getIndexData();
  const [communityRows, modelsWithArtifacts] = await Promise.all([
    getCommunityBoardRows(),
    getIndexModelsWithArtifacts(index.models),
  ]);
  const resolutionContext = familyResolutionContext(modelsWithArtifacts);
  const resolvedCommunityRows = communityRows === null
    ? []
    : communityRowsWithFamilyPaths(communityRows, resolutionContext);

  return (
    <main className="mx-auto w-full max-w-[1480px] px-5 py-7 lg:px-8">
      <FamilyDirectory
        communityRows={resolvedCommunityRows}
        models={index.models}
        resolutionContext={resolutionContext}
      />
    </main>
  );
}
