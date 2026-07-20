import { orgLogoForFamilyName, orgLogoForModelLabel } from "@/lib/family-logo";

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
      width={size}
      height={size}
      loading="lazy"
      className={`inline-block shrink-0 rounded-sm ${className ?? ""}`}
    />
  );
}
