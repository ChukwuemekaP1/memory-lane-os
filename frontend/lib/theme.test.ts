import { describe, expect, it } from "vitest";

import { applyTokens, clearTokens, mergeTokens } from "./theme";

function fakeRoot() {
  const values = new Map<string, string>();
  return {
    element: {
      style: {
        setProperty: (key: string, value: string) => values.set(key, value),
        removeProperty: (key: string) => values.delete(key),
      },
    } as unknown as HTMLElement,
    values,
  };
}

describe("mergeTokens", () => {
  it("layers defaults, base, and overrides", () => {
    expect(mergeTokens({ accent: "#111" }, { font: "serif" })).toEqual({
      accent: "#111",
      background: "#fffbeb",
      font: "serif",
    });
  });
});

describe("applyTokens / clearTokens", () => {
  it("writes only known, sane values as CSS variables", () => {
    const { element, values } = fakeRoot();
    applyTokens({ accent: "#123456", evil: "x".repeat(100) }, element);
    expect(values.get("--ml-accent")).toBe("#123456");
    expect(values.has("--ml-background")).toBe(false);
    clearTokens(element);
    expect(values.size).toBe(0);
  });
});
