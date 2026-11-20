"use client";

import { Monitor, Moon, Sun } from "lucide-react";

import { AnimatePresence, motion } from "@/components/ui/motion";
import { type ColorSchemePreference, useColorScheme } from "@/lib/color-scheme";
import { cn } from "@/lib/utils";

/**
 * Space-constrained two-state header toggle (SiteHeader & AppShell).
 * Switches to the opposite of the currently rendered scheme and clears
 * localStorage when returning to the OS default.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const { resolved, mounted, toggle } = useColorScheme();
  const isDark = mounted && resolved === "dark";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      title={isDark ? "Switch to warm paper light theme" : "Switch to candlelit dark theme"}
      className={cn(
        "glass-pill relative inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[var(--foreground)] transition-colors hover:border-[var(--ring)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] sm:h-10 sm:w-10",
        className,
      )}
    >
      <AnimatePresence mode="wait" initial={false}>
        {isDark ? (
          <motion.span
            key="moon"
            initial={{ opacity: 0, rotate: -45, scale: 0.75 }}
            animate={{ opacity: 1, rotate: 0, scale: 1 }}
            exit={{ opacity: 0, rotate: 45, scale: 0.75 }}
            transition={{ duration: 0.18 }}
            className="inline-flex items-center justify-center text-[var(--gold)]"
          >
            <Moon className="h-4 w-4" />
          </motion.span>
        ) : (
          <motion.span
            key="sun"
            initial={{ opacity: 0, rotate: 45, scale: 0.75 }}
            animate={{ opacity: 1, rotate: 0, scale: 1 }}
            exit={{ opacity: 0, rotate: -45, scale: 0.75 }}
            transition={{ duration: 0.18 }}
            className="inline-flex items-center justify-center text-[var(--bronze)]"
          >
            <Sun className="h-4 w-4" />
          </motion.span>
        )}
      </AnimatePresence>
      <span className="sr-only">{isDark ? "Switch to light theme" : "Switch to dark theme"}</span>
    </button>
  );
}

/**
 * Explicit three-state control ("Light", "Dark", "System (Currently ...)")
 * for the /app/account settings page.
 */
export function ThemePreferencePicker() {
  const { preference, systemScheme, mounted, setPreference } = useColorScheme();

  const options: {
    value: ColorSchemePreference;
    label: string;
    sublabel: string;
    icon: typeof Sun;
  }[] = [
    {
      value: "light",
      label: "Warm Paper",
      sublabel: "Linen cream & woodland ink",
      icon: Sun,
    },
    {
      value: "dark",
      label: "Candlelit Dark",
      sublabel: "Deep obsidian & antique gold",
      icon: Moon,
    },
    {
      value: "system",
      label: "System",
      sublabel: mounted ? `Currently ${systemScheme}` : "Follows your device",
      icon: Monitor,
    },
  ];

  return (
    <div
      role="radiogroup"
      aria-label="Color theme preference"
      className="grid gap-3 sm:grid-cols-3"
    >
      {options.map((opt) => {
        const Icon = opt.icon;
        const active = (mounted ? preference : "system") === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setPreference(opt.value)}
            className={cn(
              "flex items-start gap-3 rounded-[var(--radius)] border p-4 text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
              active
                ? "border-[var(--primary)] bg-[var(--sage)]/55 shadow-sm ring-1 ring-[var(--ring)]/30"
                : "border-[var(--border)] bg-[var(--card)]/70 hover:border-[var(--ring)]",
            )}
          >
            <span
              className={cn(
                "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
                active
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                  : "bg-[var(--secondary)] text-[var(--foreground)]",
              )}
            >
              <Icon className="h-4 w-4" />
            </span>
            <div>
              <p className="font-display text-base font-medium text-[var(--foreground)]">
                {opt.label}
              </p>
              <p className="mt-0.5 text-xs text-[var(--muted-foreground)]">{opt.sublabel}</p>
            </div>
          </button>
        );
      })}
    </div>
  );
}
