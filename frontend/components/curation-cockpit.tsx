"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Check,
  CheckCircle2,
  Copy,
  Globe,
  Link2,
  Lock,
  Plus,
  RotateCcw,
  Settings2,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";

import { ScheduleManager } from "@/components/schedule-manager";
import { SpaceCoverBand, SpaceNav, useSpace } from "@/components/space-provider";
import { ThemeSettings } from "@/components/theme-settings";
import { Button } from "@/components/ui/button";
import { AnimatedTabs, GlassCard } from "@/components/ui/motion";
import { apiRequest } from "@/lib/api";
import { EDITORIAL_THEMES, type EditorialThemePreset } from "@/lib/covers";
import {
  ApiError,
  listContributions,
  mintGuestToken,
  moderateContribution,
  patchSpace,
  type ContributionCard,
} from "@/lib/spaces";

type CockpitTab = "review" | "share";
type ReviewFilter = "pending" | "visible" | "rejected";

export function CurationCockpit({ spaceId }: { spaceId: string }) {
  const { space, token, reload } = useSpace();
  const searchParams = useSearchParams();
  const justCreated = searchParams.get("created") === "1";

  const isStaff = space.my_role === "owner" || space.my_role === "collaborator";
  const [tab, setTab] = useState<CockpitTab>(justCreated ? "share" : "review");
  const [filter, setFilter] = useState<ReviewFilter>("pending");
  const [items, setItems] = useState<ContributionCard[]>([]);
  const [counts, setCounts] = useState({ pending: 0, visible: 0, rejected: 0 });
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(
    justCreated ? "Your memory space is live! Share your guest link below." : null,
  );
  const [error, setError] = useState<string | null>(null);

  // Share & Settings state
  const [guestLink, setGuestLink] = useState<string | null>(null);
  const [viewerLink, setViewerLink] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [minting, setMinting] = useState<string | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);

  const loadQueue = useCallback(async () => {
    if (!isStaff) return;
    setLoading(true);
    setError(null);
    try {
      const [pend, vis, rej] = await Promise.all([
        listContributions(spaceId, { status: "pending", limit: 50 }, token),
        listContributions(spaceId, { status: "visible", limit: 50 }, token),
        listContributions(spaceId, { status: "rejected", limit: 50 }, token),
      ]);
      setCounts({
        pending: pend.items.length,
        visible: vis.items.length,
        rejected: rej.items.length,
      });
      setItems(
        filter === "pending" ? pend.items : filter === "visible" ? vis.items : rej.items,
      );
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not load moderation queue.");
    } finally {
      setLoading(false);
    }
  }, [spaceId, token, filter, isStaff]);

  useEffect(() => {
    if (tab === "review") void loadQueue();
  }, [tab, loadQueue]);

  async function handleModerate(id: string, action: "approve" | "reject" | "restore") {
    setError(null);
    try {
      await moderateContribution(id, action, undefined, token);
      setToast(
        action === "approve"
          ? "Contribution approved and published to the album."
          : action === "reject"
            ? "Contribution moved to rejected."
            : "Contribution restored to the album.",
      );
      await loadQueue();
      reload();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not update submission.");
    }
  }

  async function handleMint(role_cap: "contributor" | "viewer") {
    setMinting(role_cap);
    setError(null);
    try {
      const res = await mintGuestToken(
        spaceId,
        {
          role_cap,
          label: role_cap === "contributor" ? "Guest contribution link" : "Album viewer link",
        },
        token,
      );
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      const urlObj = new URL(res.url, origin || "http://localhost:3000");
      const rawGuest = urlObj.searchParams.get("guest") || urlObj.searchParams.get("token") || "";
      const finalUrl =
        role_cap === "contributor"
          ? `${origin}/s/${spaceId}/contribute?guest=${encodeURIComponent(rawGuest)}`
          : `${origin}/s/${spaceId}?guest=${encodeURIComponent(rawGuest)}`;
      if (role_cap === "contributor") setGuestLink(finalUrl);
      else setViewerLink(finalUrl);
      setToast(`Fresh ${role_cap} link ready to share.`);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not mint share link.");
    } finally {
      setMinting(null);
    }
  }

  async function copyToClipboard(label: string, value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      setToast("Copy failed — select the link manually.");
    }
  }

  async function updateSpaceField(body: Record<string, unknown>, message: string) {
    setSavingSettings(true);
    setError(null);
    try {
      await patchSpace(spaceId, body, token);
      setToast(message);
      reload();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not save setting.");
    } finally {
      setSavingSettings(false);
    }
  }

  async function applyEditorialPreset(preset: EditorialThemePreset) {
    setSavingSettings(true);
    try {
      await apiRequest(`/v1/spaces/${spaceId}/settings`, {
        method: "PATCH",
        body: {
          custom_tokens: {
            accent: preset.accent,
            background: preset.background,
            editorial_theme: preset.name,
          },
        },
        token,
      });
      setToast(`Applied ${preset.name} palette.`);
      reload();
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not update theme.");
    } finally {
      setSavingSettings(false);
    }
  }

  if (!isStaff) {
    return (
      <div>
        <SpaceCoverBand spaceId={spaceId} />
        <main className="site-frame py-8">
          <SpaceNav spaceId={spaceId} active="/settings" />
          <GlassCard className="p-8 text-center text-sm text-[var(--muted-foreground)]">
            Host curation and settings are available to the space owner and collaborators.
          </GlassCard>
        </main>
      </div>
    );
  }

  return (
    <div className="pb-20">
      <SpaceCoverBand spaceId={spaceId} />
      <main className="site-frame py-8">
        <SpaceNav spaceId={spaceId} active="/settings" />

        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <AnimatedTabs
            layoutId="cockpit-tab"
            value={tab}
            onChange={setTab}
            items={[
              {
                value: "review",
                label: "Review Queue",
                icon: <ShieldCheck className="h-4 w-4" />,
                count: counts.pending,
              },
              {
                value: "share",
                label: "Share & Settings",
                icon: <Settings2 className="h-4 w-4" />,
              },
            ]}
          />
        </div>

        {toast && (
          <p
            role="status"
            className="mb-5 rounded-[var(--radius)] border border-[var(--primary)]/20 bg-[var(--sage)]/65 px-4 py-3 text-sm font-medium text-[var(--primary)]"
          >
            {toast}
          </p>
        )}
        {error && (
          <p role="alert" className="mb-5 rounded-[var(--radius)] bg-red-50 px-4 py-3 text-sm text-red-900">
            {error}
          </p>
        )}

        {tab === "review" ? (
          <div className="flex flex-col gap-5">
            <AnimatedTabs
              layoutId="review-filter"
              value={filter}
              onChange={setFilter}
              items={[
                { value: "pending", label: "Pending Review", count: counts.pending },
                { value: "visible", label: "Approved", count: counts.visible },
                { value: "rejected", label: "Rejected", count: counts.rejected },
              ]}
            />

            {loading ? (
              <div className="glass-panel h-40 animate-pulse rounded-[var(--radius)]" />
            ) : items.length === 0 ? (
              <GlassCard className="p-10 text-center">
                <p className="font-display text-2xl font-medium">All caught up</p>
                <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                  No submissions in this queue right now.
                </p>
              </GlassCard>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {items.map((item) => (
                  <GlassCard key={item.id} className="flex flex-col gap-3 p-5">
                    <div className="flex items-baseline justify-between gap-2">
                      <p className="font-semibold">{item.display_name ?? "Anonymous guest"}</p>
                      <span className="eyebrow rounded-full bg-[var(--secondary)] px-2.5 py-0.5 text-[var(--muted-foreground)]">
                        {item.kind}
                      </span>
                    </div>
                    {item.body && (
                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--foreground)]">
                        {item.body}
                      </p>
                    )}
                    <div className="mt-auto flex flex-wrap gap-2 border-t border-[var(--border)]/70 pt-3">
                      {filter !== "visible" && (
                        <Button
                          type="button"
                          onClick={() => handleModerate(item.id, filter === "pending" ? "approve" : "restore")}
                        >
                          <CheckCircle2 className="h-4 w-4" />
                          Approve
                        </Button>
                      )}
                      {filter !== "rejected" && (
                        <Button
                          type="button"
                          variant="destructive"
                          onClick={() => handleModerate(item.id, "reject")}
                        >
                          <XCircle className="h-4 w-4" />
                          Reject
                        </Button>
                      )}
                      {filter === "visible" && (
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => handleModerate(item.id, "reject")}
                        >
                          <RotateCcw className="h-4 w-4" />
                          Hide from album
                        </Button>
                      )}
                    </div>
                  </GlassCard>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            {/* Link Distribution Center */}
            <GlassCard className="flex flex-col gap-4 p-6">
              <div>
                <p className="eyebrow text-[var(--bronze)]">Share without sign-in</p>
                <h2 className="mt-1 font-display text-2xl font-medium">Link Distribution Center</h2>
                <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                  Mint revocable links for guests to contribute photos &amp; stories or view the finished album.
                </p>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-[var(--radius)] border border-[var(--border)] bg-white/65 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
                      <Link2 className="h-4 w-4 text-[var(--primary)]" />
                      Guest Contribution Link
                    </span>
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={minting === "contributor"}
                      onClick={() => handleMint("contributor")}
                    >
                      <Plus className="h-3.5 w-3.5" />
                      {minting === "contributor" ? "Creating…" : "Generate link"}
                    </Button>
                  </div>
                  {guestLink && (
                    <div className="mt-3 flex items-center gap-2">
                      <code className="flex-1 truncate rounded-lg bg-[var(--secondary)] px-3 py-2 text-xs">
                        {guestLink}
                      </code>
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => copyToClipboard("guest", guestLink)}
                      >
                        {copied === "guest" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                      </Button>
                    </div>
                  )}
                </div>

                <div className="rounded-[var(--radius)] border border-[var(--border)] bg-white/65 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5 text-sm font-semibold">
                      <Globe className="h-4 w-4 text-[var(--primary)]" />
                      Album Viewer Link
                    </span>
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={minting === "viewer"}
                      onClick={() => handleMint("viewer")}
                    >
                      <Plus className="h-3.5 w-3.5" />
                      {minting === "viewer" ? "Creating…" : "Generate link"}
                    </Button>
                  </div>
                  {viewerLink && (
                    <div className="mt-3 flex items-center gap-2">
                      <code className="flex-1 truncate rounded-lg bg-[var(--secondary)] px-3 py-2 text-xs">
                        {viewerLink}
                      </code>
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => copyToClipboard("viewer", viewerLink)}
                      >
                        {copied === "viewer" ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            </GlassCard>

            {/* Quick Privacy, AI Opt-In & Editorial Palette */}
            <div className="grid gap-6 md:grid-cols-2">
              <GlassCard className="flex flex-col gap-4 p-6">
                <h2 className="font-display text-2xl font-medium">Privacy &amp; AI Studio</h2>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant={space.space.visibility === "link" ? "primary" : "secondary"}
                    disabled={savingSettings}
                    onClick={() =>
                      updateSpaceField(
                        { visibility: "link", contribution_policy: "link_contributors" },
                        "Album is now accessible to anyone with a share link.",
                      )
                    }
                  >
                    <Globe className="h-4 w-4" />
                    Link access
                  </Button>
                  <Button
                    type="button"
                    variant={space.space.visibility === "private" ? "primary" : "secondary"}
                    disabled={savingSettings}
                    onClick={() =>
                      updateSpaceField({ visibility: "private" }, "Album is now private to staff.")
                    }
                  >
                    <Lock className="h-4 w-4" />
                    Private
                  </Button>
                </div>
                <div className="pt-2">
                  <Button
                    type="button"
                    variant={space.space.ai_opt_in ? "primary" : "secondary"}
                    disabled={savingSettings}
                    onClick={() =>
                      updateSpaceField(
                        { ai_opt_in: !space.space.ai_opt_in },
                        space.space.ai_opt_in ? "AI Studio disabled." : "AI Studio enabled for this space.",
                      )
                    }
                  >
                    <Sparkles className="h-4 w-4" />
                    {space.space.ai_opt_in ? "AI Memory Studio: Enabled" : "Enable AI Memory Studio"}
                  </Button>
                </div>
              </GlassCard>

              <GlassCard className="flex flex-col gap-4 p-6">
                <h2 className="font-display text-2xl font-medium">Editorial Palette</h2>
                <div className="grid gap-2.5 sm:grid-cols-3">
                  {EDITORIAL_THEMES.map((preset) => (
                    <button
                      key={preset.name}
                      type="button"
                      disabled={savingSettings}
                      onClick={() => applyEditorialPreset(preset)}
                      className="flex flex-col items-start gap-2 rounded-[var(--radius)] border border-[var(--border)] bg-white/70 p-3 text-left transition-all hover:border-[var(--ring)]"
                    >
                      <span
                        className="h-6 w-6 rounded-full border border-black/10"
                        style={{ background: preset.swatchVar }}
                      />
                      <span className="font-display text-sm font-medium">{preset.name}</span>
                    </button>
                  ))}
                </div>
              </GlassCard>
            </div>

            {/* Existing Theme Customizer & Scheduled Reveal Manager */}
            <GlassCard className="p-6">
              <ThemeSettings spaceId={spaceId} />
            </GlassCard>
            <GlassCard className="p-6">
              <ScheduleManager spaceId={spaceId} />
            </GlassCard>
          </div>
        )}
      </main>
    </div>
  );
}
