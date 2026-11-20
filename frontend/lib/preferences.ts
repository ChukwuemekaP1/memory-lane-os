/** Client-side default space & studio preferences customized in /app/account. */

import type { EditorialThemeName } from "@/lib/covers";

export interface UserPreferences {
  defaultTheme: EditorialThemeName;
  defaultVisibility: "link" | "private";
  defaultAiOptIn: boolean;
  defaultPreModeration: boolean;
  defaultAllowAnonymous: boolean;
  timezone: string;
}

const STORAGE_KEY = "ml-user-preferences-v1";

export const DEFAULT_PREFERENCES: UserPreferences = {
  defaultTheme: "Botanical",
  defaultVisibility: "link",
  defaultAiOptIn: true,
  defaultPreModeration: false,
  defaultAllowAnonymous: true,
  timezone: "Africa/Lagos",
};

export function loadUserPreferences(): UserPreferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFERENCES;
    const parsed = JSON.parse(raw) as Partial<UserPreferences>;
    return { ...DEFAULT_PREFERENCES, ...parsed };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export function saveUserPreferences(prefs: UserPreferences): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    /* ignore storage quota errors */
  }
}
