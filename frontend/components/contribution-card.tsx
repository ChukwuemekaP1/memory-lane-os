"use client";

import { useState } from "react";
import { Lock, Maximize2, MessageCircle } from "lucide-react";

import { motion } from "@/components/ui/motion";
import { toggleReaction, type ContributionDetail } from "@/lib/spaces";

function formatDate(value: string | null): string {
  if (!value) return "";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

const QUICK_REACTIONS = ["❤", "🎉", "👏", "😂"];

export function ContributionCard({
  item,
  token,
  onOpen,
}: {
  item: ContributionDetail;
  token: string | undefined;
  onOpen?: (item: ContributionDetail) => void;
}) {
  const [reactions, setReactions] = useState(item.reactions);
  const [failed, setFailed] = useState(false);
  const firstMedia = item.attachments.find((attachment) => attachment.kind !== "other");
  const previewUrl = firstMedia
    ? firstMedia.urls.derivatives.preview ?? firstMedia.urls.original
    : undefined;

  async function react(emoji: string) {
    const mine = reactions.find((entry) => entry.emoji === emoji)?.mine ?? false;
    setFailed(false);
    try {
      const result = await toggleReaction(item.id, emoji, !mine, token);
      if (result && "reactions" in result) {
        setReactions(result.reactions);
      } else if (mine) {
        setReactions((curr) =>
          curr
            .map((r) => (r.emoji === emoji ? { ...r, count: Math.max(0, r.count - 1), mine: false } : r))
            .filter((r) => r.count > 0),
        );
      }
    } catch {
      setFailed(true);
    }
  }

  return (
    <motion.article
      whileHover={{ y: -3 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className="space-card flex flex-col"
    >
      {previewUrl && firstMedia?.kind !== "audio" && (
        <button
          type="button"
          onClick={() => onOpen?.(item)}
          className="group relative overflow-hidden bg-[var(--shadow-ink)] text-left"
          aria-label={`Open media from ${item.display_name ?? "Anonymous"}`}
        >
          {firstMedia?.kind === "video" ? (
            <video
              src={previewUrl}
              preload="metadata"
              className="aspect-[16/10] w-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
            />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={previewUrl}
              alt={firstMedia?.caption ?? `Memory from ${item.display_name ?? "Anonymous"}`}
              loading="lazy"
              className="aspect-[16/10] w-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
            />
          )}
          <span className="glass-dark absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-full opacity-0 transition-opacity duration-200 group-hover:opacity-100">
            <Maximize2 className="h-3.5 w-3.5" />
          </span>
        </button>
      )}

      {firstMedia?.kind === "audio" && previewUrl && (
        <div className="border-b border-[var(--border)] bg-[var(--sage)]/35 px-4 py-3">
          <p className="eyebrow mb-1.5 text-[var(--primary)]">Voice note</p>
          <audio controls src={previewUrl} className="w-full" />
        </div>
      )}

      <div className="flex flex-1 flex-col gap-3 p-5">
        {item.is_private_to_owner && (
          <span className="eyebrow inline-flex w-fit items-center gap-1 rounded-full bg-[var(--marigold)]/70 px-2.5 py-0.5 text-[var(--foreground)]">
            <Lock className="h-3 w-3" />
            Private to host
          </span>
        )}

        {item.body && (
          <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-[var(--foreground)]">
            <span className="mr-1 font-display text-xl leading-none text-[var(--bronze)]">&ldquo;</span>
            {item.body}
            <span className="ml-0.5 font-display text-xl leading-none text-[var(--bronze)]">&rdquo;</span>
          </p>
        )}

        <div className="mt-auto flex items-baseline justify-between gap-3 border-t border-[var(--border)]/70 pt-3">
          <p className="text-sm font-semibold text-[var(--foreground)]">
            {item.display_name ?? "Anonymous guest"}
          </p>
          <time className="shrink-0 text-xs text-[var(--muted-foreground)]">
            {formatDate(item.taken_at ?? item.created_at)}
          </time>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {QUICK_REACTIONS.map((emoji) => {
            const entry = reactions.find((r) => r.emoji === emoji);
            const active = entry?.mine ?? false;
            return (
              <motion.button
                key={emoji}
                type="button"
                whileTap={{ scale: 0.88 }}
                onClick={() => react(emoji)}
                aria-pressed={active}
                className={`inline-flex min-h-[34px] items-center gap-1 rounded-full border px-2.5 text-xs font-medium transition-colors ${
                  active
                    ? "border-[var(--primary)] bg-[var(--primary)] text-[var(--primary-foreground)]"
                    : "border-[var(--border)] bg-white/60 hover:border-[var(--ring)]"
                }`}
              >
                <span>{emoji}</span>
                {entry && entry.count > 0 && <span>{entry.count}</span>}
              </motion.button>
            );
          })}
          {item.reply_count > 0 && (
            <button
              type="button"
              onClick={() => onOpen?.(item)}
              className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            >
              <MessageCircle className="h-3.5 w-3.5" />
              {item.reply_count}
            </button>
          )}
        </div>
        {failed && <p className="text-xs text-red-700">Could not update reaction.</p>}
      </div>
    </motion.article>
  );
}
