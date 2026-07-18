export function huggingFaceRepoUrl(repoId: string): string {
  const components = repoId.split("/", 2);
  return `https://huggingface.co/${encodeURIComponent(components[0] ?? "")}/${encodeURIComponent(components[1] ?? "")}`;
}
