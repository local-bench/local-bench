import type { Metadata } from "next";

export function pageMetadata(title: string, description: string): Metadata {
  return {
    title,
    description,
    alternates: { canonical: "./" },
    openGraph: { title, description, url: "./" },
  };
}

export function serializeJsonLd(value: object): string {
  return JSON.stringify(value).replaceAll("<", "\\u003c");
}
