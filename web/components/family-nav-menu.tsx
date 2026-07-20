"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { familySlug } from "@/lib/family-slug";

type FamilyNavDisclosure = {
  open: boolean;
};

type FamilyNavEscapeEvent = {
  readonly currentTarget: FamilyNavDisclosure;
  readonly key: string;
  preventDefault(): void;
};

type FamilyNavFocusTarget = {
  focus(): void;
};

type FamilyNavClickEvent = {
  readonly currentTarget: FamilyNavDisclosure;
  readonly target: EventTarget;
};

type FamilyNavContainment = {
  containsTarget(target: EventTarget | null): boolean;
};

export function FamilyNavMenu({ families }: { readonly families: readonly string[] }) {
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const summaryRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const details = detailsRef.current;
    if (details === null) return;
    return listenForFamilyNavOutsideClicks(document, details, {
      containsTarget: (target) => target instanceof Node && details.contains(target),
    });
  }, []);

  return (
    <details
      ref={detailsRef}
      className="relative w-full sm:w-auto"
      onClick={closeFamilyNavOnLinkActivation}
      onKeyDown={(event) => closeFamilyNavOnEscape(event, summaryRef.current)}
    >
      <summary
        ref={summaryRef}
        className="cursor-pointer list-none font-medium text-bench-text hover:text-bench-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-bench-accent [&::-webkit-details-marker]:hidden"
      >
        Model families
      </summary>
      <div className="z-30 mt-2 max-h-[60vh] w-full overflow-y-auto rounded border border-bench-line bg-bench-panel p-1 sm:absolute sm:left-0 sm:w-64">
        <Link href="/families" className="sticky top-0 z-10 block rounded bg-bench-panel px-3 py-2 font-semibold text-bench-text hover:bg-white/[0.04] hover:text-bench-accent">
          All families →
        </Link>
        <div className="border-t border-bench-line pt-1">
          {families.map((family) => (
            <Link
              key={family}
              href={`/families/${familySlug(family)}`}
              className="block rounded px-3 py-2 text-bench-muted hover:bg-white/[0.04] hover:text-bench-text"
            >
              {family}
            </Link>
          ))}
        </div>
      </div>
    </details>
  );
}

export function closeFamilyNavOnEscape(
  event: FamilyNavEscapeEvent,
  summary: FamilyNavFocusTarget | null,
): void {
  if (event.key !== "Escape" || !event.currentTarget.open) return;
  event.preventDefault();
  event.currentTarget.open = false;
  summary?.focus();
}

export function closeFamilyNavOnOutsideClick(
  event: Pick<Event, "target">,
  disclosure: FamilyNavDisclosure,
  containment: FamilyNavContainment,
): void {
  if (!containment.containsTarget(event.target)) disclosure.open = false;
}

export function listenForFamilyNavOutsideClicks(
  source: EventTarget,
  disclosure: FamilyNavDisclosure,
  containment: FamilyNavContainment,
): () => void {
  const handleClick = (event: Event): void => closeFamilyNavOnOutsideClick(event, disclosure, containment);
  source.addEventListener("click", handleClick);
  return () => source.removeEventListener("click", handleClick);
}

export function closeFamilyNavOnLinkActivation(event: FamilyNavClickEvent): void {
  const target = event.target;
  if (hasClosest(target) && target.closest("a") !== null) event.currentTarget.open = false;
}

function hasClosest(target: EventTarget): target is EventTarget & { closest(selectors: string): unknown } {
  return "closest" in target && typeof target.closest === "function";
}
