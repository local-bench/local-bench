import { orgLogoForModelLabel } from "@/lib/family-logo";

// Small org mark next to a model name. Decorative (alt is empty — the model name it sits
// beside carries the meaning); the org name is exposed as a title tooltip. Renders nothing
// when the label doesn't carry a first-party org name, so callers keep their color-dot
// fallback and community fine-tunes are never stamped with the base org's logo.
export function FamilyLogoMark({
  modelLabel,
  size = 16,
  className,
}: {
  readonly modelLabel: string | null | undefined;
  readonly size?: number;
  readonly className?: string;
}) {
  const logo = orgLogoForModelLabel(modelLabel);
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
