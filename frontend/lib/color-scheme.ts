"use client";

import { useCallback, useEffect, useState } from "react";

export type ColorSchemePreference = "system" | "light" | "dark";
export type ResolvedColorScheme = "light" | "dark";

const STORAGE_KEY = "color-scheme";

function getSystemScheme(): ResolvedColorScheme {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "light";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function readStoredColorScheme(): ColorSchemePreference {
  if (typeof window === "undefined") return "system";
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === "light" || raw === "dark") return raw;
  } catch {
    /* localStorage blocked */
  }
  return "system";
}

export function applyColorSchemeToDocument(pref: ColorSchemePreference): void {
  if (typeof document === "undefined") return;
  const meta = document.querySelector<HTMLMetaElement>('meta[name="color-scheme"]');
  const metaValue = pref === "system" ? "light dark" : pref;
  if (meta) {
    meta.content = metaValue;
  }
  if (pref === "system") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = pref;
  }
}

export function persistColorScheme(pref: ColorSchemePreference): void {
  applyColorSchemeToDocument(pref);
  if (typeof window === "undefined") return;
  try {
    if (pref === "system") {
      window.localStorage.removeItem(STORAGE_KEY);
    } else {
      window.localStorage.setItem(STORAGE_KEY, pref);
    }
    window.dispatchEvent(new CustomEvent("ml-color-scheme-change", { detail: pref }));
  } catch {
    /* ignore storage errors */
  }
}

/**
 * Two-state toggle logic per `dark-mode-toggle` guidance:
 * 1. Target = opposite of currently rendered scheme.
 * 2. If target differs from current system preference, store it literally ("light" | "dark").
 * 3. If target matches current system preference, remove the stored value ("system") so
 *    we don't invisibly pin the scheme against future OS changes.
 */
export function toggleOppositeColorScheme(): {
  preference: ColorSchemePreference;
  resolved: ResolvedColorScheme;
} {
  const system = getSystemScheme();
  const stored = readStoredColorScheme();
  const currentRendered: ResolvedColorScheme = stored === "system" ? system : stored;
  const target: ResolvedColorScheme = currentRendered === "dark" ? "light" : "dark";
  const nextPref: ColorSchemePreference = target === system ? "system" : target;
  persistColorScheme(nextPref);
  return { preference: nextPref, resolved: target };
}

export function useColorScheme() {
  const [preference, setPreferenceState] = useState<ColorSchemePreference>("system");
  const [systemScheme, setSystemScheme] = useState<ResolvedColorScheme>("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const initialPref = readStoredColorScheme();
    setPreferenceState(initialPref);
    setSystemScheme(getSystemScheme());
    applyColorSchemeToDocument(initialPref);

    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onMediaChange = (event: MediaQueryListEvent) => {
      // Per `dark-mode-toggle`: NEVER delete stored value when OS changes to match it.
      setSystemScheme(event.matches ? "dark" : "light");
    };
    mql.addEventListener("change", onMediaChange);

    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key === STORAGE_KEY) {
        const next = readStoredColorScheme();
        setPreferenceState(next);
        applyColorSchemeToDocument(next);
      }
    };
    window.addEventListener("storage", onStorage);

    const onCustom = () => {
      setPreferenceState(readStoredColorScheme());
    };
    window.addEventListener("ml-color-scheme-change", onCustom);

    return () => {
      mql.removeEventListener("change", onMediaChange);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("ml-color-scheme-change", onCustom);
    };
  }, []);

  const resolved: ResolvedColorScheme =
    preference === "system" ? systemScheme : preference;

  const setPreference = useCallback((next: ColorSchemePreference) => {
    persistColorScheme(next);
    setPreferenceState(next);
  }, []);

  const toggle = useCallback(() => {
    const result = toggleOppositeColorScheme();
    setPreferenceState(result.preference);
  }, []);

  return {
    preference,
    resolved,
    systemScheme,
    mounted,
    setPreference,
    toggle,
  };
}
