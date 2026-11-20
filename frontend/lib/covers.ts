/** Editorial cover imagery and theme palette mapping for occasions & spaces. */

export type EditorialThemeName = "Botanical" | "Terracotta" | "Golden Hour";

export interface EditorialThemePreset {
  name: EditorialThemeName;
  className: string;
  swatchVar: string;
  accent: string;
  background: string;
  description: string;
}

export const EDITORIAL_THEMES: EditorialThemePreset[] = [
  {
    name: "Botanical",
    className: "theme-Botanical",
    swatchVar: "var(--sage)",
    accent: "#2e5440",
    background: "#faf8f4",
    description: "Soft sage linen & woodland ink",
  },
  {
    name: "Terracotta",
    className: "theme-Terracotta",
    swatchVar: "var(--rose)",
    accent: "#8c5438",
    background: "#fbf7f4",
    description: "Warm rose blush & burnished bronze",
  },
  {
    name: "Golden Hour",
    className: "theme-Golden-Hour",
    swatchVar: "var(--marigold)",
    accent: "#8b6928",
    background: "#fcf9f2",
    description: "Sunlit marigold glow & fine stationery",
  },
];

const COVER_BY_OCCASION: Record<string, string> = {
  wedding: "/covers/wedding.jpg",
  birthday: "/covers/birthday.jpg",
  graduation: "/covers/graduation.jpg",
  anniversary: "/covers/anniversary.jpg",
  family: "/covers/family.jpg",
  tribute: "/covers/family.jpg",
  other: "/covers/hero.jpg",
};

export function coverForOccasion(occasion?: string | null): string {
  const key = (occasion ?? "other").toLowerCase().trim();
  return COVER_BY_OCCASION[key] ?? "/covers/hero.jpg";
}

export function themeClassForTokens(accent?: string | null): string {
  const value = (accent ?? "").toLowerCase();
  if (value.includes("e11d") || value.includes("8c54") || value.includes("ea58") || value.includes("rose")) {
    return "theme-Terracotta";
  }
  if (value.includes("f59e") || value.includes("b453") || value.includes("8b69") || value.includes("gold")) {
    return "theme-Golden-Hour";
  }
  return "theme-Botanical";
}

export function occasionLabel(occasion?: string | null): string {
  if (!occasion) return "Celebration";
  return occasion.charAt(0).toUpperCase() + occasion.slice(1);
}
