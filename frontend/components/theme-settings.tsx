"use client";

import { useEffect, useState } from "react";

import { SpaceNav, useSpace } from "@/components/space-provider";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  listThemes,
  patchSpace,
  previewTheme,
  type ThemeCatalogEntry,
  type ThemeTokens,
} from "@/lib/spaces";
import { applyTokens } from "@/lib/theme";

export function ThemeSettings({ spaceId }: { spaceId: string }) {
  const { space, token, reload } = useSpace();
  const [themes, setThemes] = useState<ThemeCatalogEntry[]>([]);
  const [selected, setSelected] = useState("");
  const [accent, setAccent] = useState("");
  const [background, setBackground] = useState("");
  const [font, setFont] = useState("");
  const [preview, setPreview] = useState<ThemeTokens | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    listThemes()
      .then(setThemes)
      .catch(() => setError("Could not load themes."));
  }, []);

  function overrides(): ThemeTokens {
    const result: ThemeTokens = {};
    if (accent.trim()) result.accent = accent.trim();
    if (background.trim()) result.background = background.trim();
    if (font.trim()) result.font = font.trim();
    return result;
  }

  async function onPreview() {
    setError(null);
    try {
      const result = await previewTheme(
        spaceId,
        { theme_id: selected || undefined, overrides: overrides() },
        token,
      );
      setPreview(result.tokens);
      applyTokens(result.tokens);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Preview failed.");
    }
  }

  async function onSave() {
    setError(null);
    setSaved(false);
    try {
      await patchSpace(
        spaceId,
        { ...(selected ? { theme_id: selected } : {}), theme_overrides: overrides() },
        token,
      );
      setSaved(true);
      reload();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not save the theme.");
    }
  }

  if (!space.my_permissions.includes("edit_space")) {
    return (
      <main className="mx-auto w-full max-w-2xl px-6 py-8">
        <p className="rounded-xl bg-black/5 px-4 py-6 text-center text-sm">
          Settings are available to the host and co-hosts.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-6 py-8">
      <SpaceNav spaceId={spaceId} active="" />
      <h1 className="text-2xl font-bold">Space theme</h1>
      <p className="text-sm opacity-70">
        Themes only change colors and typography — memories and permissions are never affected.
      </p>
      <label className="flex flex-col gap-1 text-sm">
        Template
        <select
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
          className="min-h-[44px] rounded-xl border border-black/15 bg-white/80 px-3"
        >
          <option value="">Keep current</option>
          {themes.map((theme) => (
            <option key={theme.id} value={theme.id} disabled={!theme.entitled}>
              {theme.name}
              {theme.entitled ? "" : " (premium)"}
            </option>
          ))}
        </select>
      </label>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-sm">
          Accent color
          <input
            value={accent}
            onChange={(event) => setAccent(event.target.value)}
            placeholder="#f59e0b"
            maxLength={40}
            className="min-h-[44px] rounded-xl border border-black/15 bg-white/80 px-4"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Background
          <input
            value={background}
            onChange={(event) => setBackground(event.target.value)}
            placeholder="#fffbeb"
            maxLength={40}
            className="min-h-[44px] rounded-xl border border-black/15 bg-white/80 px-4"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Font
          <input
            value={font}
            onChange={(event) => setFont(event.target.value)}
            placeholder="system-ui"
            maxLength={40}
            className="min-h-[44px] rounded-xl border border-black/15 bg-white/80 px-4"
          />
        </label>
      </div>
      {preview && (
        <div
          role="status"
          className="rounded-xl border border-black/10 p-4"
          style={{ background: preview.background, color: "#111" }}
        >
          <p className="text-lg font-bold" style={{ color: preview.accent }}>
            Preview headline
          </p>
          <p className="text-sm" style={{ fontFamily: preview.font }}>
            This is how memories will feel in this theme.
          </p>
        </div>
      )}
      {error && (
        <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-900">
          {error}
        </p>
      )}
      {saved && (
        <p role="status" className="rounded-xl bg-green-50 px-4 py-3 text-sm text-green-900">
          Theme saved.
        </p>
      )}
      <div className="flex gap-2">
        <Button type="button" variant="secondary" onClick={onPreview}>
          Preview
        </Button>
        <Button type="button" onClick={onSave}>
          Save theme
        </Button>
      </div>
    </main>
  );
}
