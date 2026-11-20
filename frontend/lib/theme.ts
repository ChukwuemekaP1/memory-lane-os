/** Theme tokens: merge base + overrides, apply as CSS variables. */

import type { ThemeTokens } from "./spaces";

export const DEFAULT_TOKENS: Required<Pick<ThemeTokens, "accent" | "background" | "font">> = {
  accent: "#f59e0b",
  background: "#fffbeb",
  font: "system-ui",
};

export function mergeTokens(base: ThemeTokens, overrides: ThemeTokens = {}): ThemeTokens {
  return { ...DEFAULT_TOKENS, ...base, ...overrides };
}

const VAR_MAP: Record<string, string> = {
  accent: "--ml-accent",
  background: "--ml-background",
  font: "--ml-font",
};

export function applyTokens(tokens: ThemeTokens, root: HTMLElement = document.documentElement): void {
  for (const [key, variable] of Object.entries(VAR_MAP)) {
    const value = tokens[key];
    if (typeof value === "string" && value.length > 0 && value.length <= 40) {
      root.style.setProperty(variable, value);
    }
  }
}

export function clearTokens(root: HTMLElement = document.documentElement): void {
  for (const variable of Object.values(VAR_MAP)) {
    root.style.removeProperty(variable);
  }
}
