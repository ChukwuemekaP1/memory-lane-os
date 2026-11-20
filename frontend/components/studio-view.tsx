"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  Check,
  CheckCircle2,
  Code2,
  Download,
  FileAudio,
  Film,
  ImagePlus,
  Loader2,
  Mail,
  Pencil,
  Sparkles,
  Tags,
  Trash2,
  Wand2,
} from "lucide-react";

import { SpaceCoverBand, SpaceNav, useSpace } from "@/components/space-provider";
import { Button } from "@/components/ui/button";
import { GlassCard, StaggerGrid, StaggerItem } from "@/components/ui/motion";
import { ApiError } from "@/lib/api";
import { getContribution, listContributions } from "@/lib/spaces";
import {
  cancelAIJob,
  createBookPdfArchive,
  deleteAIAsset,
  getAICapabilities,
  getAIQuota,
  listAIAssets,
  listAIJobs,
  patchAIAsset,
  promoteAIAsset,
  runAIJob,
  type AIAsset,
  type AICapabilities,
  type AIJob,
  type AIQuota,
} from "@/lib/studio";

interface SpaceMediaOption {
  asset_id: string;
  kind: string;
  mime: string;
  author: string;
  previewUrl?: string;
}

const TOOLS = [
  {
    value: "summary",
    label: "Memory Summary",
    desc: "Weaves visible memories into a heartfelt narrative summary.",
    icon: Sparkles,
  },
  {
    value: "categorization",
    label: "Story Grouping",
    desc: "Categorizes memories with filterable tags automatically.",
    icon: Tags,
  },
  {
    value: "captions",
    label: "Caption & Image Analysis",
    desc: "Grounded captions and descriptions for uploaded photos.",
    icon: Wand2,
  },
  {
    value: "transcription",
    label: "Voice Note Transcripts",
    desc: "Transcribes uploaded voice notes cleanly with OpenRouter audio.",
    icon: FileAudio,
  },
  {
    value: "story_enhancement",
    label: "Story Enhancement",
    desc: "Polishes collected notes into a cohesive keepsake story.",
    icon: Pencil,
  },
  {
    value: "letter",
    label: "Memory & Thank-You Letter",
    desc: "Drafts a personal letter referencing real submitted memories.",
    icon: Mail,
  },
  {
    value: "book",
    label: "Digital Memory Book",
    desc: "Generates structured chapters ready for PDF book export.",
    icon: BookOpen,
  },
  {
    value: "highlight_film",
    label: "Highlight Film",
    desc: "AI moment selection + real FFmpeg MP4 video assembly.",
    icon: Film,
  },
  {
    value: "image_generation",
    label: "Keepsake Artwork",
    desc: "Generates custom artwork stored directly in Neon Object Storage.",
    icon: ImagePlus,
  },
];

export function StudioView({ spaceId }: { spaceId: string }) {
  const { space, token } = useSpace();
  const canRun = space.my_permissions.includes("run_ai");
  const [jobs, setJobs] = useState<AIJob[]>([]);
  const [assets, setAssets] = useState<AIAsset[]>([]);
  const [quota, setQuota] = useState<AIQuota | null>(null);
  const [capabilities, setCapabilities] = useState<AICapabilities | null>(null);
  const [mediaOptions, setMediaOptions] = useState<SpaceMediaOption[]>([]);

  const [kind, setKind] = useState("summary");
  const [selectedAssetIds, setSelectedAssetIds] = useState<string[]>([]);
  const [language, setLanguage] = useState("en");
  const [tone, setTone] = useState("warm");
  const [letterTo, setLetterTo] = useState("");
  const [letterFrom, setLetterFrom] = useState("All of us");
  const [bookTitle, setBookTitle] = useState(`${space.space.title} — Memory Book`);
  const [bookSections, setBookSections] = useState("Shared Moments, Heartfelt Wishes, Looking Ahead");
  const [maxDuration, setMaxDuration] = useState(30);
  const [imagePrompt, setImagePrompt] = useState(
    `Warm watercolor botanical keepsake card for ${space.space.title}`,
  );
  const [imageTitle, setImageTitle] = useState("Keepsake Artwork");
  const [showRawJson, setShowRawJson] = useState(false);
  const [rawJson, setRawJson] = useState("{}");

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [running, setRunning] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [jobList, assetList, quotaInfo, capInfo] = await Promise.all([
        listAIJobs(spaceId, token),
        listAIAssets(spaceId, token),
        getAIQuota(spaceId, token),
        getAICapabilities(spaceId, token).catch(() => null),
      ]);
      setJobs(jobList);
      setAssets(assetList);
      setQuota(quotaInfo);
      if (capInfo) setCapabilities(capInfo);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not load the studio.");
    }
  }, [spaceId, token]);

  useEffect(() => {
    if (!canRun) return;
    void refresh();
    // Load real uploaded media from this space for visual pickers
    listContributions(spaceId, { kind: "media,audio", limit: 30 }, token)
      .then(async (page) => {
        const detailed = await Promise.all(
          page.items.map((c) => getContribution(c.id, token).catch(() => null)),
        );
        const opts: SpaceMediaOption[] = [];
        for (const item of detailed) {
          if (!item) continue;
          for (const att of item.attachments) {
            if (att.status === "ready") {
              opts.push({
                asset_id: att.asset_id,
                kind: att.kind,
                mime: att.mime,
                author: item.display_name ?? "Guest",
                previewUrl: att.urls.derivatives.thumb ?? att.urls.derivatives.preview ?? att.urls.original,
              });
            }
          }
        }
        setMediaOptions(opts);
      })
      .catch(() => undefined);
  }, [canRun, refresh, spaceId, token]);

  useEffect(() => {
    if (!canRun) return;
    const hasActive = jobs.some((job) => job.status === "queued" || job.status === "running");
    if (!hasActive) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [canRun, jobs, refresh]);

  if (!canRun) {
    return (
      <div>
        <SpaceCoverBand spaceId={spaceId} />
        <main className="site-frame py-8">
          <SpaceNav spaceId={spaceId} active="/studio" />
          <GlassCard className="p-8 text-center text-sm text-[var(--muted-foreground)]">
            AI Memory Studio is available to the host and collaborators.
          </GlassCard>
        </main>
      </div>
    );
  }

  function buildPayload(): Record<string, unknown> {
    if (showRawJson) {
      return JSON.parse(rawJson || "{}") as Record<string, unknown>;
    }
    switch (kind) {
      case "captions":
        return { asset_ids: selectedAssetIds };
      case "transcription":
        return { asset_ids: selectedAssetIds, language };
      case "highlight_film":
        return { asset_ids: selectedAssetIds, max_duration_s: maxDuration };
      case "story_enhancement":
        return { tone };
      case "letter":
        return { to: letterTo.trim() || "Friend", from: letterFrom.trim() || "All of us", tone };
      case "book":
        return {
          title: bookTitle.trim() || "Memory Book",
          sections: bookSections
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
            .map((title) => ({ title })),
        };
      case "image_generation":
        return { prompt: imagePrompt.trim(), title: imageTitle.trim() || "Keepsake Artwork" };
      default:
        return {};
    }
  }

  function toggleAsset(id: string) {
    setSelectedAssetIds((curr) =>
      curr.includes(id) ? curr.filter((x) => x !== id) : [...curr, id],
    );
  }

  async function run() {
    setError(null);
    setNotice(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = buildPayload();
    } catch {
      setError("Advanced JSON must be valid JSON.");
      return;
    }
    if (
      (kind === "captions" || kind === "transcription" || kind === "highlight_film") &&
      !showRawJson &&
      selectedAssetIds.length === 0
    ) {
      setError("Select at least one uploaded media item from this space first.");
      return;
    }
    setRunning(true);
    try {
      await runAIJob(spaceId, kind, parsed, token);
      setNotice("AI job submitted to OpenRouter — status updates automatically below.");
      await refresh();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not start the job.");
    } finally {
      setRunning(false);
    }
  }

  async function saveEdit() {
    if (!editing) return;
    try {
      await patchAIAsset(editing.id, { text_body: editing.text }, token);
      setEditing(null);
      setNotice("Saved your edits.");
      await refresh();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not save.");
    }
  }

  const activeCap = capabilities?.capabilities[kind];
  const isUnavailable = Boolean(activeCap && !activeCap.available);

  const filteredMedia = mediaOptions.filter((m) => {
    if (kind === "captions") return m.kind === "image";
    if (kind === "transcription") return m.kind === "audio";
    if (kind === "highlight_film") return m.kind === "image" || m.kind === "video";
    return false;
  });

  return (
    <div className="pb-20">
      <SpaceCoverBand spaceId={spaceId} />
      <main className="site-frame py-8">
        <SpaceNav spaceId={spaceId} active="/studio" />

        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="eyebrow text-[var(--bronze)]">Powered by OpenRouter</p>
            <h2 className="mt-1 font-display text-3xl font-medium sm:text-4xl">AI Memory Studio</h2>
          </div>
          {quota && (
            <div className="glass-pill rounded-full px-4 py-2 text-xs font-medium text-[var(--muted-foreground)]">
              Monthly budget:{" "}
              <strong className="text-[var(--foreground)]">
                {quota.used.toLocaleString()} / {quota.limit.toLocaleString()}
              </strong>{" "}
              tokens
            </div>
          )}
        </div>

        {/* Tool Cards Grid */}
        <StaggerGrid className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {TOOLS.map((tool) => {
            const Icon = tool.icon;
            const selected = kind === tool.value;
            const cap = capabilities?.capabilities[tool.value];
            return (
              <StaggerItem key={tool.value}>
                <button
                  type="button"
                  onClick={() => {
                    setKind(tool.value);
                    setSelectedAssetIds([]);
                    setError(null);
                  }}
                  className={`flex h-full w-full flex-col items-start gap-2 rounded-[var(--radius)] border p-4 text-left transition-all ${
                    selected
                      ? "border-[var(--primary)] bg-[var(--sage)]/55 shadow-sm ring-2 ring-[var(--ring)]/30"
                      : "glass-panel hover:border-[var(--ring)]"
                  }`}
                >
                  <div className="flex w-full items-center justify-between gap-2">
                    <span
                      className={`flex h-9 w-9 items-center justify-center rounded-full ${
                        selected
                          ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                          : "bg-[var(--secondary)] text-[var(--primary)]"
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                    </span>
                    {cap && (
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                          cap.available
                            ? "bg-[var(--sage)] text-[var(--primary)]"
                            : "bg-red-100 text-red-800"
                        }`}
                      >
                        {cap.available ? "Ready" : "Unavailable"}
                      </span>
                    )}
                  </div>
                  <p className="font-display text-lg font-medium">{tool.label}</p>
                  <p className="text-xs leading-relaxed text-[var(--muted-foreground)]">{tool.desc}</p>
                </button>
              </StaggerItem>
            );
          })}
        </StaggerGrid>

        {/* Visual Tool Runner */}
        <GlassCard className="mb-8 flex flex-col gap-4 p-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="font-display text-2xl font-medium">
                {TOOLS.find((t) => t.value === kind)?.label}
              </h3>
              {activeCap && (
                <p className="text-xs text-[var(--muted-foreground)]">
                  {activeCap.available
                    ? `Active model: ${activeCap.model} (${capabilities?.provider})`
                    : `Unavailable: ${activeCap.reason ?? "Not configured."}`}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => {
                if (!showRawJson) setRawJson(JSON.stringify(buildPayload(), null, 2));
                setShowRawJson((v) => !v);
              }}
              className="glass-pill inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-[var(--muted-foreground)]"
            >
              <Code2 className="h-3.5 w-3.5" />
              {showRawJson ? "Visual controls" : "Advanced JSON"}
            </button>
          </div>

          {showRawJson ? (
            <label className="field">
              Parameters (JSON)
              <textarea
                value={rawJson}
                onChange={(e) => setRawJson(e.target.value)}
                rows={4}
                spellCheck={false}
                className="font-mono text-xs"
              />
            </label>
          ) : (
            <div className="flex flex-col gap-4">
              {(kind === "summary" || kind === "categorization") && (
                <p className="text-sm text-[var(--muted-foreground)]">
                  Automatically uses all approved, non-private memories in <strong>{space.space.title}</strong>.
                </p>
              )}

              {(kind === "captions" || kind === "transcription" || kind === "highlight_film") && (
                <div className="flex flex-col gap-2">
                  <p className="text-sm font-semibold">
                    Select uploaded {kind === "transcription" ? "voice notes" : kind === "captions" ? "photos" : "photos & videos"} ({selectedAssetIds.length} selected)
                  </p>
                  {filteredMedia.length === 0 ? (
                    <p className="rounded-[var(--radius)] bg-[var(--secondary)] px-4 py-3 text-xs text-[var(--muted-foreground)]">
                      No ready {kind === "transcription" ? "audio" : "photo/video"} uploads in this space yet. Upload one via Contribute first.
                    </p>
                  ) : (
                    <div className="grid gap-2.5 sm:grid-cols-2 md:grid-cols-3">
                      {filteredMedia.map((m) => {
                        const checked = selectedAssetIds.includes(m.asset_id);
                        return (
                          <button
                            key={m.asset_id}
                            type="button"
                            onClick={() => toggleAsset(m.asset_id)}
                            className={`flex items-center gap-3 rounded-[var(--radius)] border p-2.5 text-left transition-all ${
                              checked
                                ? "border-[var(--primary)] bg-[var(--sage)]/55 ring-2 ring-[var(--ring)]/30"
                                : "border-[var(--border)] bg-white/70 hover:border-[var(--ring)]"
                            }`}
                          >
                            {m.kind === "image" && m.previewUrl ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={m.previewUrl} alt="" className="h-12 w-12 rounded-lg object-cover" />
                            ) : (
                              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-[var(--secondary)] text-[var(--primary)]">
                                {m.kind === "audio" ? <FileAudio className="h-5 w-5" /> : <Film className="h-5 w-5" />}
                              </span>
                            )}
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-xs font-semibold">{m.author}</p>
                              <p className="truncate text-[11px] text-[var(--muted-foreground)]">{m.mime}</p>
                            </div>
                            {checked && <Check className="h-4 w-4 shrink-0 text-[var(--primary)]" />}
                          </button>
                        );
                      })}
                    </div>
                  )}
                  {kind === "transcription" && (
                    <label className="field max-w-xs pt-1">
                      Spoken language
                      <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                        <option value="en">English (en)</option>
                        <option value="fr">French (fr)</option>
                        <option value="es">Spanish (es)</option>
                        <option value="yo">Yoruba (yo)</option>
                        <option value="ig">Igbo (ig)</option>
                        <option value="ha">Hausa (ha)</option>
                      </select>
                    </label>
                  )}
                  {kind === "highlight_film" && (
                    <label className="field max-w-xs pt-1">
                      Max duration: {maxDuration} seconds
                      <input
                        type="range"
                        min={10}
                        max={90}
                        step={5}
                        value={maxDuration}
                        onChange={(e) => setMaxDuration(Number(e.target.value))}
                      />
                    </label>
                  )}
                </div>
              )}

              {kind === "story_enhancement" && (
                <label className="field max-w-xs">
                  Editorial tone
                  <select value={tone} onChange={(e) => setTone(e.target.value)}>
                    <option value="warm">Warm &amp; heartfelt</option>
                    <option value="poetic">Poetic &amp; timeless</option>
                    <option value="joyful">Joyful &amp; celebratory</option>
                    <option value="reflective">Reflective &amp; calm</option>
                  </select>
                </label>
              )}

              {kind === "letter" && (
                <div className="grid gap-3 sm:grid-cols-3">
                  <label className="field">
                    Recipient (To)
                    <input value={letterTo} onChange={(e) => setLetterTo(e.target.value)} placeholder="e.g., Ada" />
                  </label>
                  <label className="field">
                    Signed by (From)
                    <input value={letterFrom} onChange={(e) => setLetterFrom(e.target.value)} placeholder="All of us" />
                  </label>
                  <label className="field">
                    Tone
                    <select value={tone} onChange={(e) => setTone(e.target.value)}>
                      <option value="warm">Warm</option>
                      <option value="grateful">Grateful (Thank-you)</option>
                      <option value="celebratory">Celebratory</option>
                      <option value="poetic">Poetic</option>
                    </select>
                  </label>
                </div>
              )}

              {kind === "book" && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="field">
                    Book title
                    <input value={bookTitle} onChange={(e) => setBookTitle(e.target.value)} />
                  </label>
                  <label className="field">
                    Chapters (comma-separated)
                    <input value={bookSections} onChange={(e) => setBookSections(e.target.value)} />
                  </label>
                </div>
              )}

              {kind === "image_generation" && (
                <div className="flex flex-col gap-3">
                  <label className="field">
                    Artwork title
                    <input value={imageTitle} onChange={(e) => setImageTitle(e.target.value)} />
                  </label>
                  <label className="field">
                    Creative prompt
                    <textarea rows={3} value={imagePrompt} onChange={(e) => setImagePrompt(e.target.value)} />
                  </label>
                </div>
              )}
            </div>
          )}

          <div className="flex items-center gap-3 pt-1">
            <Button type="button" onClick={run} disabled={running || isUnavailable}>
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {running ? "Submitting…" : "Run with OpenRouter"}
            </Button>
          </div>
          {error && (
            <p role="alert" className="rounded-[var(--radius)] bg-red-50 px-4 py-3 text-sm text-red-900">
              {error}
            </p>
          )}
          {notice && (
            <p role="status" className="rounded-[var(--radius)] bg-[var(--sage)]/60 px-4 py-3 text-sm text-[var(--primary)]">
              {notice}
            </p>
          )}
        </GlassCard>

        {/* Job History */}
        <section aria-label="Jobs" className="mb-8 flex flex-col gap-3">
          <h3 className="font-display text-2xl font-medium">Processing Queue &amp; History</h3>
          {jobs.length === 0 ? (
            <p className="text-sm text-[var(--muted-foreground)]">No AI jobs run yet.</p>
          ) : (
            <div className="flex flex-col gap-2">
              {jobs.map((job) => (
                <div
                  key={job.id}
                  className="glass-panel flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius)] px-4 py-3 text-sm"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    {(job.status === "queued" || job.status === "running") && (
                      <Loader2 className="h-4 w-4 animate-spin text-[var(--primary)]" />
                    )}
                    <span className="font-semibold capitalize">{job.kind.replace("_", " ")}</span>
                    <span className="rounded-full bg-[var(--secondary)] px-2.5 py-0.5 text-xs font-medium">
                      {job.status}
                    </span>
                    {job.model && (
                      <span className="text-xs text-[var(--muted-foreground)]">{job.model}</span>
                    )}
                    {(typeof job.input_tokens === "number" || typeof job.output_tokens === "number") && (
                      <span className="text-xs text-[var(--muted-foreground)]">
                        {(job.input_tokens ?? 0) + (job.output_tokens ?? 0)} tok
                      </span>
                    )}
                    {typeof job.cost_usd === "number" && (
                      <span className="text-xs font-medium text-[var(--bronze)]">
                        ${job.cost_usd.toFixed(5)}
                      </span>
                    )}
                    {job.last_error && <span className="text-xs text-red-700">— {job.last_error}</span>}
                  </div>
                  {(job.status === "queued" || job.status === "running") && (
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => cancelAIJob(job.id, token).then(refresh)}
                    >
                      Cancel
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Generated Keepsake Assets */}
        <section aria-label="Generated assets" className="flex flex-col gap-3">
          <h3 className="font-display text-2xl font-medium">Generated Keepsakes</h3>
          {assets.length === 0 ? (
            <GlassCard className="p-8 text-center text-sm text-[var(--muted-foreground)]">
              Generated summaries, letters, transcripts, books, artwork, and highlight films will appear here for your review.
            </GlassCard>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {assets.map((asset) => (
                <GlassCard key={asset.id} className="flex flex-col gap-3 p-5">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-display text-xl font-medium">{asset.title ?? asset.kind}</p>
                      <span className="eyebrow text-[var(--muted-foreground)]">
                        AI-assisted {asset.is_promoted ? "· Published" : "· Draft"}
                      </span>
                    </div>
                  </div>
                  {editing?.id === asset.id ? (
                    <textarea
                      value={editing.text}
                      onChange={(event) => setEditing({ id: asset.id, text: event.target.value })}
                      rows={6}
                      className="rounded-[var(--radius)] border border-[var(--border)] bg-white px-3 py-2 text-sm"
                    />
                  ) : (
                    asset.text_body && (
                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--foreground)]">
                        {asset.text_body.slice(0, 700)}
                      </p>
                    )
                  )}
                  <div className="mt-auto flex flex-wrap gap-2 border-t border-[var(--border)]/70 pt-3">
                    {editing?.id === asset.id ? (
                      <Button type="button" onClick={saveEdit}>
                        Save edits
                      </Button>
                    ) : (
                      asset.text_body && (
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => setEditing({ id: asset.id, text: asset.text_body ?? "" })}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                          Edit
                        </Button>
                      )
                    )}
                    {asset.asset_id && (
                      <a
                        href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api"}/v1/media/${asset.asset_id}/download`}
                        target="_blank"
                        rel="noreferrer"
                        className="glass-pill inline-flex min-h-[44px] items-center gap-1.5 rounded-[var(--radius)] px-4 text-sm font-medium"
                      >
                        <Download className="h-4 w-4" />
                        Download
                      </a>
                    )}
                    {asset.kind === "book" && (
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() =>
                          createBookPdfArchive(spaceId, token)
                            .then(() => setNotice("PDF memory book archive queued."))
                            .catch((f: unknown) =>
                              setError(f instanceof ApiError ? f.message : "Could not export PDF book."),
                            )
                        }
                      >
                        <BookOpen className="h-3.5 w-3.5" />
                        Export PDF
                      </Button>
                    )}
                    {!asset.is_promoted && (
                      <Button
                        type="button"
                        onClick={() => promoteAIAsset(asset.id, token).then(refresh)}
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Approve &amp; Publish
                      </Button>
                    )}
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => deleteAIAsset(asset.id, token).then(refresh)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      Discard
                    </Button>
                  </div>
                </GlassCard>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
