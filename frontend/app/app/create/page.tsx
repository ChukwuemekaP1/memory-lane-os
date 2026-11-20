"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Cake,
  Check,
  Globe,
  GraduationCap,
  Heart,
  Leaf,
  Lock,
  Sparkles,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { AnimatePresence, FadeInUp, GlassCard, motion } from "@/components/ui/motion";
import { apiRequest } from "@/lib/api";
import {
  coverForOccasion,
  EDITORIAL_THEMES,
  type EditorialThemeName,
} from "@/lib/covers";
import { loadUserPreferences } from "@/lib/preferences";
import { ApiError, createSpace, listThemes, type ThemeCatalogEntry } from "@/lib/spaces";

const OCCASIONS = [
  { value: "wedding", label: "Wedding", icon: Heart, desc: "Toasts, candid moments & blessings" },
  { value: "birthday", label: "Birthday", icon: Cake, desc: "Wishes, throwbacks & voice notes" },
  { value: "graduation", label: "Graduation", icon: GraduationCap, desc: "Letters & milestones from loved ones" },
  { value: "anniversary", label: "Anniversary", icon: Sparkles, desc: "Stories across the years together" },
  { value: "family", label: "Family", icon: Users, desc: "Living heirloom archive for everyone" },
  { value: "other", label: "Other", icon: Leaf, desc: "Farewells, tributes, or custom albums" },
] as const;

function AppCreateSpaceWizardInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialOccasion = searchParams.get("occasion") || "wedding";

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [occasion, setOccasion] = useState<string>(
    OCCASIONS.some((o) => o.value === initialOccasion) ? initialOccasion : "wedding",
  );
  const [title, setTitle] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [locationLabel, setLocationLabel] = useState("");
  const [description, setDescription] = useState("");
  const [selectedTheme, setSelectedTheme] = useState<EditorialThemeName>("Botanical");
  const [visibility, setVisibility] = useState<"link" | "private">("link");
  const [aiOptIn, setAiOptIn] = useState(true);
  const [preModeration, setPreModeration] = useState(false);
  const [allowAnonymous, setAllowAnonymous] = useState(true);
  const [timezone, setTimezone] = useState("Africa/Lagos");

  const [themes, setThemes] = useState<ThemeCatalogEntry[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const prefs = loadUserPreferences();
    setSelectedTheme(prefs.defaultTheme);
    setVisibility(prefs.defaultVisibility);
    setAiOptIn(prefs.defaultAiOptIn);
    setPreModeration(prefs.defaultPreModeration);
    setAllowAnonymous(prefs.defaultAllowAnonymous);
    setTimezone(prefs.timezone);

    listThemes()
      .then((catalog) => setThemes(catalog.filter((t) => t.entitled)))
      .catch(() => undefined);
  }, []);

  function pickBackendThemeId(): string {
    const match = themes.find((t) => t.occasions?.includes(occasion));
    return (match ?? themes[0])?.id ?? "";
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!title.trim()) {
      setError("Please give your memory space a title.");
      setStep(2);
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const themeId = pickBackendThemeId();
      if (!themeId) {
        throw new Error("Could not load available themes. Please sign in and try again.");
      }
      const created = await createSpace({
        title: title.trim(),
        occasion,
        theme_id: themeId,
      });
      const spaceId = created.space.id;
      const preset = EDITORIAL_THEMES.find((t) => t.name === selectedTheme) ?? EDITORIAL_THEMES[0];

      await apiRequest(`/v1/spaces/${spaceId}`, {
        method: "PATCH",
        body: {
          description: description.trim() || null,
          event_date: eventDate || null,
          location_label: locationLabel.trim() || null,
          visibility,
          contribution_policy: "link_contributors",
          ai_opt_in: aiOptIn,
        },
      }).catch(() => undefined);

      await apiRequest(`/v1/spaces/${spaceId}/settings`, {
        method: "PATCH",
        body: {
          custom_tokens: {
            accent: preset.accent,
            background: preset.background,
            editorial_theme: preset.name,
            timezone,
          },
          pre_moderation: preModeration,
          allow_anonymous: allowAnonymous,
        },
      }).catch(() => undefined);

      router.push(`/s/${spaceId}/settings?created=1`);
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) {
        router.push("/login?mode=signin&next=/app/create");
        return;
      }
      setError(failure instanceof Error ? failure.message : "Could not create your space.");
      setSubmitting(false);
    }
  }

  const coverUrl = coverForOccasion(occasion);

  return (
    <main className="site-frame py-8 sm:py-12">
      <FadeInUp className="mx-auto max-w-3xl">
        {/* Stepper Header */}
        <div className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="eyebrow text-[var(--bronze)]">New memory space</p>
            <h1 className="mt-1 font-display text-4xl font-medium leading-tight">
              Craft your keepsake album
            </h1>
          </div>
          <ol className="glass-panel inline-flex items-center gap-1.5 rounded-full p-1.5 text-xs font-semibold">
            {[
              { n: 1 as const, label: "Occasion" },
              { n: 2 as const, label: "Details" },
              { n: 3 as const, label: "Theme & Privacy" },
            ].map((s) => (
              <li key={s.n}>
                <button
                  type="button"
                  onClick={() => (s.n < step || (s.n === 2 && occasion) ? setStep(s.n) : undefined)}
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 transition-all ${
                    step === s.n
                      ? "bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm"
                      : step > s.n
                        ? "bg-[var(--sage)] text-[var(--primary)]"
                        : "text-[var(--muted-foreground)]"
                  }`}
                >
                  {step > s.n ? <Check className="h-3.5 w-3.5" /> : <span>{s.n}</span>}
                  <span className="hidden sm:inline">{s.label}</span>
                </button>
              </li>
            ))}
          </ol>
        </div>

        {/* Live Atmospheric Preview Strip */}
        <div className="cover-band mb-6 rounded-[var(--radius)] p-6 shadow-md">
          <img src={coverUrl} alt={occasion} className="cover-img" />
          <div className="relative z-10 flex flex-wrap items-end justify-between gap-4">
            <div>
              <span className="glass-dark eyebrow inline-block rounded-full px-3 py-1 text-[var(--gold)]">
                {occasion}
              </span>
              <p className="mt-2 font-display text-2xl font-medium text-white sm:text-3xl">
                {title.trim() || "Your celebration title"}
              </p>
              {description.trim() && (
                <p className="mt-1 max-w-xl text-sm text-white/80 line-clamp-2">{description}</p>
              )}
            </div>
            <span className="glass-dark rounded-full px-3 py-1 text-xs font-medium">
              {selectedTheme} · {visibility === "link" ? "Link access" : "Private"}
            </span>
          </div>
        </div>

        <GlassCard className="p-6 sm:p-8">
          <form onSubmit={handleSubmit}>
            <AnimatePresence mode="wait">
              {step === 1 && (
                <motion.div
                  key="step-1"
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 12 }}
                  transition={{ duration: 0.24 }}
                  className="flex flex-col gap-5"
                >
                  <div>
                    <h2 className="font-display text-2xl font-medium">What are we celebrating?</h2>
                    <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                      Selecting an occasion sets the initial atmospheric cover artwork.
                    </p>
                  </div>
                  <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
                    {OCCASIONS.map((item) => {
                      const Icon = item.icon;
                      const active = occasion === item.value;
                      return (
                        <motion.button
                          key={item.value}
                          type="button"
                          whileHover={{ y: -3 }}
                          whileTap={{ scale: 0.98 }}
                          onClick={() => setOccasion(item.value)}
                          className={`flex flex-col items-start gap-2 rounded-[var(--radius)] border p-4 text-left transition-all ${
                            active
                              ? "border-[var(--primary)] bg-[var(--sage)]/55 shadow-sm ring-2 ring-[var(--ring)]/30"
                              : "border-[var(--border)] bg-white/60 hover:border-[var(--ring)]"
                          }`}
                        >
                          <span
                            className={`flex h-10 w-10 items-center justify-center rounded-full ${
                              active
                                ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                                : "bg-[var(--secondary)] text-[var(--foreground)]"
                            }`}
                          >
                            <Icon className="h-5 w-5" />
                          </span>
                          <span className="font-display text-lg font-medium">{item.label}</span>
                          <span className="text-xs text-[var(--muted-foreground)]">{item.desc}</span>
                        </motion.button>
                      );
                    })}
                  </div>
                  <div className="flex justify-end pt-2">
                    <Button type="button" onClick={() => setStep(2)}>
                      Continue to details
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </div>
                </motion.div>
              )}

              {step === 2 && (
                <motion.div
                  key="step-2"
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 12 }}
                  transition={{ duration: 0.24 }}
                  className="flex flex-col gap-4"
                >
                  <div>
                    <h2 className="font-display text-2xl font-medium">Tell guests about the moment</h2>
                    <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                      This welcome note greets friends and family on the contribution page.
                    </p>
                  </div>
                  <label className="field">
                    Space title
                    <input
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      required
                      maxLength={120}
                      placeholder="e.g., Emma & James's Wedding or Ada's 30th"
                    />
                  </label>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="field">
                      Event date (optional)
                      <input
                        type="date"
                        value={eventDate}
                        onChange={(e) => setEventDate(e.target.value)}
                      />
                    </label>
                    <label className="field">
                      Location (optional)
                      <input
                        value={locationLabel}
                        onChange={(e) => setLocationLabel(e.target.value)}
                        maxLength={120}
                        placeholder="e.g., Lagos Botanical Gardens"
                      />
                    </label>
                  </div>
                  <label className="field">
                    Welcome note / prompt for guests
                    <textarea
                      rows={4}
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      maxLength={1000}
                      placeholder="What should guests share? e.g., Your favorite memory with us, candid photos, or a voice note."
                    />
                  </label>
                  <div className="flex items-center justify-between pt-2">
                    <Button type="button" variant="secondary" onClick={() => setStep(1)}>
                      <ArrowLeft className="h-4 w-4" />
                      Back
                    </Button>
                    <Button
                      type="button"
                      onClick={() => {
                        if (!title.trim()) {
                          setError("Please add a title before continuing.");
                          return;
                        }
                        setError(null);
                        setStep(3);
                      }}
                    >
                      Theme &amp; privacy
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </div>
                </motion.div>
              )}

              {step === 3 && (
                <motion.div
                  key="step-3"
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 12 }}
                  transition={{ duration: 0.24 }}
                  className="flex flex-col gap-6"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <h2 className="font-display text-2xl font-medium">Theme &amp; privacy</h2>
                      <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                        Pre-filled from your{" "}
                        <Link href="/app/account" className="underline">
                          Account defaults
                        </Link>
                        . Customize anytime in your owner cockpit.
                      </p>
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-3">
                    {EDITORIAL_THEMES.map((preset) => {
                      const active = selectedTheme === preset.name;
                      return (
                        <button
                          key={preset.name}
                          type="button"
                          onClick={() => setSelectedTheme(preset.name)}
                          className={`flex flex-col gap-2 rounded-[var(--radius)] border p-4 text-left transition-all ${
                            active
                              ? "border-[var(--primary)] bg-white/90 shadow-sm ring-2 ring-[var(--ring)]/30"
                              : "border-[var(--border)] bg-white/50 hover:border-[var(--ring)]"
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span
                              className="h-7 w-7 rounded-full border border-black/10 shadow-inner"
                              style={{ background: preset.swatchVar }}
                            />
                            {active && <Check className="h-4 w-4 text-[var(--primary)]" />}
                          </div>
                          <span className="font-display text-lg font-medium">{preset.name}</span>
                          <span className="text-xs text-[var(--muted-foreground)]">
                            {preset.description}
                          </span>
                        </button>
                      );
                    })}
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <button
                      type="button"
                      onClick={() => setVisibility("link")}
                      className={`flex items-start gap-3 rounded-[var(--radius)] border p-4 text-left transition-all ${
                        visibility === "link"
                          ? "border-[var(--primary)] bg-[var(--sage)]/45"
                          : "border-[var(--border)] bg-white/50"
                      }`}
                    >
                      <Globe className="mt-0.5 h-5 w-5 shrink-0 text-[var(--primary)]" />
                      <div>
                        <p className="text-sm font-semibold">Anyone with the link</p>
                        <p className="mt-0.5 text-xs text-[var(--muted-foreground)]">
                          Share viewer and contributor links with guests right away.
                        </p>
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={() => setVisibility("private")}
                      className={`flex items-start gap-3 rounded-[var(--radius)] border p-4 text-left transition-all ${
                        visibility === "private"
                          ? "border-[var(--primary)] bg-[var(--sage)]/45"
                          : "border-[var(--border)] bg-white/50"
                      }`}
                    >
                      <Lock className="mt-0.5 h-5 w-5 shrink-0 text-[var(--primary)]" />
                      <div>
                        <p className="text-sm font-semibold">Keep album private</p>
                        <p className="mt-0.5 text-xs text-[var(--muted-foreground)]">
                          Only you can view the album until you choose to open or reveal it.
                        </p>
                      </div>
                    </button>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="flex cursor-pointer items-start gap-3 rounded-[var(--radius)] border border-[var(--border)] bg-white/55 p-4 text-sm">
                      <input
                        type="checkbox"
                        checked={aiOptIn}
                        onChange={(e) => setAiOptIn(e.target.checked)}
                        className="mt-1 h-4 w-4 accent-[var(--primary)]"
                      />
                      <span>
                        <strong className="font-semibold">Enable AI Memory Studio</strong>
                        <span className="block text-xs text-[var(--muted-foreground)]">
                          Generate summaries, captions, transcripts, books, and highlight films.
                        </span>
                      </span>
                    </label>
                    <label className="flex cursor-pointer items-start gap-3 rounded-[var(--radius)] border border-[var(--border)] bg-white/55 p-4 text-sm">
                      <input
                        type="checkbox"
                        checked={allowAnonymous}
                        onChange={(e) => setAllowAnonymous(e.target.checked)}
                        className="mt-1 h-4 w-4 accent-[var(--primary)]"
                      />
                      <span>
                        <strong className="font-semibold">Allow anonymous notes</strong>
                        <span className="block text-xs text-[var(--muted-foreground)]">
                          Guests can submit without displaying their name publicly.
                        </span>
                      </span>
                    </label>
                  </div>

                  <div className="flex items-center justify-between pt-2">
                    <Button type="button" variant="secondary" onClick={() => setStep(2)}>
                      <ArrowLeft className="h-4 w-4" />
                      Back
                    </Button>
                    <Button type="submit" disabled={submitting}>
                      <Sparkles className="h-4 w-4" />
                      {submitting ? "Creating space…" : "Create space"}
                    </Button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {error && (
              <p role="alert" className="mt-4 rounded-[var(--radius)] bg-red-50 px-4 py-3 text-sm text-red-900">
                {error}
              </p>
            )}
          </form>
        </GlassCard>
      </FadeInUp>
    </main>
  );
}

export default function AppCreateSpacePage() {
  return (
    <Suspense
      fallback={
        <main className="site-frame py-16 text-sm text-[var(--muted-foreground)]">
          Preparing your creation studio…
        </main>
      }
    >
      <AppCreateSpaceWizardInner />
    </Suspense>
  );
}
