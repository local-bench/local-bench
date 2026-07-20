import Link from "next/link";
import { serializeJsonLd } from "@/lib/page-metadata";

export type Crumb = { readonly label: string; readonly href?: string };

export function Breadcrumbs({ items }: { readonly items: readonly Crumb[] }) {
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.label,
      ...(item.href === undefined ? {} : { item: new URL(item.href, "https://local-bench.ai").toString() }),
    })),
  };
  return (
    <>
      <nav aria-label="Breadcrumb" className="text-sm text-bench-muted">
        <ol className="flex flex-wrap items-center gap-2">
          {items.map((item, index) => (
            <li key={item.label} className="flex items-center gap-2">
              {item.href ? (
                <Link href={item.href} className="text-bench-accent hover:underline">
                  {item.label}
                </Link>
              ) : (
                <span className="text-bench-text">{item.label}</span>
              )}
              {index < items.length - 1 ? <span aria-hidden className="text-bench-muted/50">/</span> : null}
            </li>
          ))}
        </ol>
      </nav>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: serializeJsonLd(structuredData) }}
      />
    </>
  );
}
