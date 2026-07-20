import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import {
  closeFamilyNavOnEscape,
  closeFamilyNavOnLinkActivation,
  closeFamilyNavOnOutsideClick,
  FamilyNavMenu,
} from "../components/family-nav-menu";

describe("family navigation disclosure", () => {
  it("keeps native disclosure semantics and family links", () => {
    // Given: the header's ordered family list.
    const families = ["DeepSeek V3", "Qwen3.6"];

    // When: the client disclosure is rendered to markup.
    const html = renderToStaticMarkup(<FamilyNavMenu families={families} />);

    // Then: it remains a details/summary disclosure of ordinary links.
    expect(html).toContain("<details");
    expect(html).toContain("<summary");
    expect(html).toContain('href="/families/deepseek-v3"');
    expect(html).toContain('href="/families/qwen3-6"');
    expect(html).not.toContain('role="menu"');
    expect(html).not.toContain("aria-haspopup");
  });

  it("closes on Escape and returns focus to the summary", () => {
    // Given: an open disclosure with focus inside it.
    const disclosure = { open: true };
    const focus = vi.fn();
    const preventDefault = vi.fn();

    // When: Escape is handled.
    closeFamilyNavOnEscape({ key: "Escape", preventDefault }, disclosure, { focus });

    // Then: the disclosure closes and the summary regains focus.
    expect(disclosure.open).toBe(false);
    expect(preventDefault).toHaveBeenCalledOnce();
    expect(focus).toHaveBeenCalledOnce();
  });

  it("closes when a click lands outside", () => {
    // Given: an open disclosure.
    const disclosure = { open: true };

    // When: the document click target is outside the disclosure.
    closeFamilyNavOnOutsideClick(disclosure, false);

    // Then: the disclosure closes.
    expect(disclosure.open).toBe(false);
  });

  it("closes when a family link is activated", () => {
    // Given: an open disclosure.
    const disclosure = { open: true };

    // When: a link within the disclosure is activated.
    closeFamilyNavOnLinkActivation(disclosure, true);

    // Then: the disclosure closes before client-side navigation.
    expect(disclosure.open).toBe(false);
  });
});
