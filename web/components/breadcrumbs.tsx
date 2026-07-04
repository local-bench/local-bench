import Link from "next/link";

export type Crumb = { readonly label: string; readonly href?: string };

export function Breadcrumbs({ items }: { readonly items: readonly Crumb[] }) {
  return (
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
  );
}
