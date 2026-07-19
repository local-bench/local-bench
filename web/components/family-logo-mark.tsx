import { orgLogoForFamilyName, orgLogoForModelLabel } from "@/lib/family-logo";

// Small org mark next to a model name. Decorative (alt is empty — the model name it sits
// beside carries the meaning); the org name is exposed as a title tooltip.
export function FamilyLogoMark({
  familyName,
  modelLabel,
  size = 16,
  className,
}: {
  readonly familyName?: string | null;
  readonly modelLabel: string | null | undefined;
  readonly size?: number;
  readonly className?: string;
}) {
  const logo = orgLogoForFamilyName(familyName) ?? orgLogoForModelLabel(modelLabel);
  if (logo === null) {
    return null;
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- static export serves the bundled asset directly
    <img
      src={logo.src}
      alt=""
      title={logo.orgLabel}
      width={size}
      height={size}
      loading="lazy"
      className={`inline-block shrink-0 rounded-sm ${className ?? ""}`}
    />
  );
}
