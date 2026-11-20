"use client";

import { cn } from "@/lib/utils";

/**
 * Bespoke Memory Lane heirloom emblem:
 * A botanical woodland arch framing a winding golden lane and keepsake star.
 */
export function BrandMark({
  size = "md",
  showWordmark = true,
  inverted = false,
  className,
}: {
  size?: "sm" | "md" | "lg";
  showWordmark?: boolean;
  inverted?: boolean;
  className?: string;
}) {
  const iconDims =
    size === "sm" ? "h-8 w-8" : size === "lg" ? "h-11 w-11" : "h-9 w-9";
  const wordmarkSize =
    size === "sm" ? "text-lg" : size === "lg" ? "text-2xl" : "text-xl";

  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <span
        className={cn(
          "relative flex shrink-0 items-center justify-center overflow-hidden rounded-[12px] shadow-sm transition-transform duration-300 group-hover:scale-[1.04]",
          iconDims,
          inverted
            ? "bg-white/15 ring-1 ring-white/25"
            : "bg-[var(--primary)] ring-1 ring-black/10",
        )}
        aria-hidden="true"
      >
        <svg
          viewBox="0 0 40 40"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="h-full w-full"
        >
          {/* Subtle warm radial glow behind the arch */}
          <defs>
            <radialGradient id="ml-glow" cx="50%" cy="32%" r="60%">
              <stop offset="0%" stopColor="#E6C687" stopOpacity="0.32" />
              <stop offset="100%" stopColor="#E6C687" stopOpacity="0" />
            </radialGradient>
          </defs>
          <rect width="40" height="40" fill="url(#ml-glow)" />

          {/* Keepsake heirloom archway */}
          <path
            d="M11 32V19C11 14.0294 15.0294 10 20 10C24.9706 10 29 14.0294 29 19V32"
            stroke="#F5EFE6"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
          <path
            d="M14.2 32V19.4C14.2 16.0863 16.7967 13.4 20 13.4C23.2033 13.4 25.8 16.0863 25.8 19.4V32"
            stroke="#E2BF78"
            strokeOpacity="0.65"
            strokeWidth="1"
            strokeLinecap="round"
          />

          {/* Winding memory lane path */}
          <path
            d="M15.5 32C17.2 28.4 22.8 27.2 21.3 23.6C20.5 21.8 18.8 21.1 20 19.3"
            stroke="#E2BF78"
            strokeWidth="1.65"
            strokeLinecap="round"
          />
          <path
            d="M23.5 32C24.4 29.6 22.2 27.8 21.1 26.2"
            stroke="#F5EFE6"
            strokeOpacity="0.7"
            strokeWidth="1.2"
            strokeLinecap="round"
          />

          {/* Four-point keepsake star at the zenith */}
          <path
            d="M20 15.2L20.65 16.75L22.2 17.4L20.65 18.05L20 19.6L19.35 18.05L17.8 17.4L19.35 16.75L20 15.2Z"
            fill="#E8C984"
          />
        </svg>
      </span>
      {showWordmark && (
        <span
          className={cn(
            "font-display font-medium tracking-tight",
            wordmarkSize,
            inverted ? "text-white" : "text-[var(--foreground)]",
          )}
        >
          Memory Lane
        </span>
      )}
    </span>
  );
}
