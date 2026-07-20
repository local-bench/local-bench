import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import {
  closeFamilyNavOnEscape,
  closeFamilyNavOnLinkActivation,
  closeFamilyNavOnOutsideClick,
  FamilyNavMenu,
  listenForFamilyNavOutsideClicks,
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
    expect(html).toContain('href="/families/deepseek-v3/"');
    expect(html).toContain('href="/families/qwen3-6/"');
    expect(html).not.toContain('role="menu"');
    expect(html).not.toContain("aria-haspopup");
  });

  it("closes on Escape and returns focus to the summary", () => {
    // Given: an open disclosure with focus inside it.
    const disclosure = { open: true };
    const focus = vi.fn();
    const preventDefault = vi.fn();

    // When: Escape is handled.
    closeFamilyNavOnEscape({ currentTarget: disclosure, key: "Escape", preventDefault }, { focus });

    // Then: the disclosure closes and the summary regains focus.
    expect(disclosure.open).toBe(false);
    expect(preventDefault).toHaveBeenCalledOnce();
    expect(focus).toHaveBeenCalledOnce();
  });

  it("closes when a click lands outside", () => {
    // Given: an open disclosure listening to document clicks.
    const disclosure = { open: true };
    const clickSource = new EventTarget();
    const stopListening = listenForFamilyNavOutsideClicks(clickSource, disclosure, {
      containsTarget: () => false,
    });

    // When: the click source dispatches an outside click.
    clickSource.dispatchEvent(new Event("click"));

    // Then: the disclosure closes.
    expect(disclosure.open).toBe(false);
    stopListening();
  });

  it("stays open when a document click lands inside", () => {
    // Given: an open disclosure and a click target it contains.
    const disclosure = { open: true };
    const target = new EventTarget();

    // When: the outside-click controller receives the contained target.
    closeFamilyNavOnOutsideClick({ target }, disclosure, {
      containsTarget: (candidate) => candidate === target,
    });

    // Then: the disclosure stays open.
    expect(disclosure.open).toBe(true);
  });

  it("closes when a family link is activated", () => {
    // Given: an open disclosure.
    const disclosure = { open: true };

    // When: a link target within the disclosure is activated.
    closeFamilyNavOnLinkActivation({ currentTarget: disclosure, target: new FamilyNavTestTarget(true) });

    // Then: the disclosure closes before client-side navigation.
    expect(disclosure.open).toBe(false);
  });

  it("stays open when a non-link disclosure target is activated", () => {
    // Given: an open disclosure.
    const disclosure = { open: true };

    // When: a non-link target within the disclosure is activated.
    closeFamilyNavOnLinkActivation({ currentTarget: disclosure, target: new FamilyNavTestTarget(false) });

    // Then: the disclosure stays open.
    expect(disclosure.open).toBe(true);
  });
});

class FamilyNavTestTarget extends EventTarget {
  constructor(private readonly link: boolean) {
    super();
  }

  closest(selectors: string): FamilyNavTestTarget | null {
    return selectors === "a" && this.link ? this : null;
  }
}
