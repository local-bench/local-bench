"use client";

import Link from "next/link";
import {
  useEffect,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { familySlug } from "@/lib/family-slug";

type FamilyNavDisclosure = {
  open: boolean;
};

type FamilyNavEscapeEvent = {
  readonly key: string;
  preventDefault(): void;
};

type FamilyNavFocusTarget = {
  focus(): void;
};

export function FamilyNavMenu({ families }: { readonly families: readonly string[] }) {
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const summaryRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const details = detailsRef.current;
    if (details === null) return;
    const handleDocumentClick = (event: MouseEvent): void => {
      const target = event.target;
      closeFamilyNavOnOutsideClick(details, target instanceof Node && details.contains(target));
    };
    document.addEventListener("click", handleDocumentClick);
    return () => document.removeEventListener("click", handleDocumentClick);
  }, []);

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDetailsElement>): void => {
    closeFamilyNavOnEscape(event, event.currentTarget, summaryRef.current);
  };
  const handleClick = (event: ReactMouseEvent<HTMLDetailsElement>): void => {
    const target = event.target;
    closeFamilyNavOnLinkActivation(
      event.currentTarget,
      target instanceof Element && target.closest("a") !== null,
    );
  };

  return (
    <details
      ref={detailsRef}
      className="relative w-full sm:w-auto"
      onClick={handleClick}
      onKeyDown={handleKeyDown}
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
  disclosure: FamilyNavDisclosure,
  summary: FamilyNavFocusTarget | null,
): void {
  if (event.key !== "Escape" || !disclosure.open) return;
  event.preventDefault();
  disclosure.open = false;
  summary?.focus();
}

export function closeFamilyNavOnOutsideClick(
  disclosure: FamilyNavDisclosure,
  clickedInside: boolean,
): void {
  if (!clickedInside) disclosure.open = false;
}

export function closeFamilyNavOnLinkActivation(
  disclosure: FamilyNavDisclosure,
  activatedLink: boolean,
): void {
  if (activatedLink) disclosure.open = false;
}
