"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  Film,
  FolderHeart,
  Home,
  Images,
  MessageSquarePlus,
  Plus,
  Settings2,
  Sparkles,
  User,
} from "lucide-react";

import { motion } from "@/components/ui/motion";

export interface BottomTab {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  matchExact?: boolean;
  accent?: boolean;
}

export const APP_BOTTOM_TABS: BottomTab[] = [
  { href: "/app", label: "Home", icon: Home, matchExact: true },
  { href: "/app/spaces", label: "Spaces", icon: FolderHeart },
  { href: "/app/create", label: "Create", icon: Plus, accent: true },
  { href: "/app/studio", label: "Studio", icon: Sparkles },
  { href: "/app/account", label: "Account", icon: User },
];

export function MobileBottomNav({
  tabs = APP_BOTTOM_TABS,
  guestToken,
}: {
  tabs?: BottomTab[];
  guestToken?: string;
}) {
  const pathname = usePathname();

  function withToken(href: string): string {
    if (!guestToken) return href;
    return `${href}?guest=${encodeURIComponent(guestToken)}`;
  }

  return (
    <nav
      aria-label="Mobile navigation"
      className="glass-nav fixed inset-x-0 bottom-0 z-50 border-t border-[var(--border)]/80 pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <div className="mx-auto grid max-w-lg grid-cols-5 items-end px-2 py-1.5">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = tab.matchExact
            ? pathname === tab.href
            : pathname === tab.href || pathname.startsWith(`${tab.href}/`);

          if (tab.accent) {
            return (
              <Link
                key={tab.label}
                href={withToken(tab.href)}
                className="flex flex-col items-center justify-center gap-0.5 py-1"
              >
                <motion.span
                  whileTap={{ scale: 0.9 }}
                  className="flex h-11 w-11 -translate-y-1.5 items-center justify-center rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] shadow-lg ring-4 ring-[var(--background)]"
                >
                  <Icon className="h-5 w-5" />
                </motion.span>
                <span className="-mt-1 text-[10px] font-semibold text-[var(--primary)]">
                  {tab.label}
                </span>
              </Link>
            );
          }

          return (
            <Link
              key={tab.label}
              href={withToken(tab.href)}
              className={`relative flex flex-col items-center justify-center gap-0.5 rounded-2xl py-1.5 transition-colors ${
                isActive
                  ? "text-[var(--primary)]"
                  : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              }`}
            >
              <motion.span
                whileTap={{ scale: 0.88 }}
                className="relative flex h-7 w-12 items-center justify-center rounded-full"
              >
                {isActive && (
                  <motion.span
                    layoutId="mobile-bottom-active"
                    transition={{ type: "spring", stiffness: 450, damping: 32 }}
                    className="absolute inset-0 rounded-full bg-[var(--sage)]"
                  />
                )}
                <Icon className="relative z-10 h-[18px] w-[18px]" />
              </motion.span>
              <span className="text-[10px] font-semibold tracking-tight">{tab.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

export function buildSpaceBottomTabs(spaceId: string, isStaff: boolean): BottomTab[] {
  if (isStaff) {
    return [
      { href: `/s/${spaceId}`, label: "Album", icon: Home, matchExact: true },
      { href: `/s/${spaceId}/gallery`, label: "Gallery", icon: Images },
      { href: `/s/${spaceId}/contribute`, label: "Add", icon: MessageSquarePlus, accent: true },
      { href: `/s/${spaceId}/settings`, label: "Curate", icon: Settings2 },
      { href: `/s/${spaceId}/studio`, label: "Studio", icon: Sparkles },
    ];
  }
  return [
    { href: `/s/${spaceId}`, label: "Album", icon: Home, matchExact: true },
    { href: `/s/${spaceId}/gallery`, label: "Gallery", icon: Images },
    { href: `/s/${spaceId}/contribute`, label: "Add", icon: MessageSquarePlus, accent: true },
    { href: `/s/${spaceId}/timeline`, label: "Timeline", icon: BookOpen },
    { href: `/s/${spaceId}/slideshow`, label: "Slides", icon: Film },
  ];
}
