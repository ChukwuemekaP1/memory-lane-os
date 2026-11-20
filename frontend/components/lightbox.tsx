"use client";

import { useEffect } from "react";

import type { ContributionDetail } from "@/lib/spaces";

/** Full-screen media viewer with keyboard close. Single attachment focus. */
export function Lightbox({
  item,
  onClose,
}: {
  item: ContributionDetail;
  onClose: () => void;
}) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Media from ${item.display_name ?? "Anonymous"}`}
      className="fixed inset-0 z-50 flex flex-col bg-black/90 p-4 text-white"
      onClick={onClose}
    >
      <div className="flex items-center justify-between gap-4">
        <p className="truncate text-sm opacity-80">
          {item.display_name ?? "Anonymous"}
          {item.body ? ` — ${item.body.slice(0, 80)}` : ""}
        </p>
        <button
          type="button"
          onClick={onClose}
          className="min-h-[44px] min-w-[44px] rounded-full bg-white/10 text-lg"
          aria-label="Close viewer"
        >
          ×
        </button>
      </div>
      <div
        className="flex flex-1 items-center justify-center gap-4 overflow-auto py-4"
        onClick={(event) => event.stopPropagation()}
      >
        {item.attachments.map((attachment) => {
          const url = attachment.urls.derivatives.preview ?? attachment.urls.original;
          if (!url) return null;
          if (attachment.kind === "video") {
            return (
              <video key={attachment.asset_id} src={url} controls className="max-h-[75vh] max-w-full" />
            );
          }
          if (attachment.kind === "audio") {
            return <audio key={attachment.asset_id} src={url} controls className="w-full max-w-md" />;
          }
          return (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={attachment.asset_id} src={url} alt={attachment.caption ?? ""} className="max-h-[75vh] max-w-full object-contain" />
          );
        })}
      </div>
    </div>
  );
}
