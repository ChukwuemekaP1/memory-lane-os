"use client";

import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const EASE_EDITORIAL = [0.22, 1, 0.36, 1] as const;

export function MotionRoot({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}

export function FadeInUp({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: EASE_EDITORIAL }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

export function StaggerGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: 0.06 } },
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 16, scale: 0.985 },
        visible: {
          opacity: 1,
          y: 0,
          scale: 1,
          transition: { duration: 0.42, ease: EASE_EDITORIAL },
        },
      }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

export function GlassCard({
  children,
  className,
  interactive = false,
}: {
  children: ReactNode;
  className?: string;
  interactive?: boolean;
}) {
  return (
    <motion.div
      whileHover={interactive ? { y: -4, transition: { duration: 0.22, ease: EASE_EDITORIAL } } : undefined}
      whileTap={interactive ? { scale: 0.99 } : undefined}
      className={cn("glass-panel rounded-[var(--radius)]", className)}
    >
      {children}
    </motion.div>
  );
}

export interface AnimatedTabItem<T extends string = string> {
  value: T;
  label: string;
  icon?: ReactNode;
  count?: number;
}

export function AnimatedTabs<T extends string>({
  items,
  value,
  onChange,
  layoutId = "active-pill",
  className,
}: {
  items: Array<AnimatedTabItem<T>>;
  value: T;
  onChange: (next: T) => void;
  layoutId?: string;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      className={cn(
        "glass-panel inline-flex flex-wrap items-center gap-1 rounded-full p-1",
        className,
      )}
    >
      {items.map((item) => {
        const active = item.value === value;
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.value)}
            className={cn(
              "relative inline-flex min-h-[40px] items-center gap-2 rounded-full px-4 text-sm font-medium transition-colors",
              active ? "text-[var(--primary-foreground)]" : "text-[var(--foreground)]/80 hover:text-[var(--foreground)]",
            )}
          >
            {active && (
              <motion.span
                layoutId={layoutId}
                transition={{ type: "spring", stiffness: 420, damping: 32 }}
                className="absolute inset-0 rounded-full bg-[var(--primary)] shadow-sm"
              />
            )}
            <span className="relative z-10 inline-flex items-center gap-1.5">
              {item.icon}
              {item.label}
              {typeof item.count === "number" && (
                <span
                  className={cn(
                    "ml-0.5 rounded-full px-2 py-0.5 text-[11px] font-semibold",
                    active ? "bg-white/20 text-white" : "bg-black/5 text-[var(--muted-foreground)]",
                  )}
                >
                  {item.count}
                </span>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function SuccessCheckmark({ className }: { className?: string }) {
  return (
    <motion.div
      initial={{ scale: 0.6, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 320, damping: 22 }}
      className={cn(
        "mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] shadow-lg",
        className,
      )}
    >
      <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth={2.6}>
        <motion.path
          d="M5 13l4 4L19 7"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.45, delay: 0.12, ease: EASE_EDITORIAL }}
        />
      </svg>
    </motion.div>
  );
}

export { AnimatePresence, motion };
