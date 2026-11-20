"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FolderHeart, Home, Plus, Sparkles, User } from "lucide-react";

import { BrandMark } from "@/components/brand-mark";
import { APP_BOTTOM_TABS, MobileBottomNav } from "@/components/mobile-bottom-nav";
import { motion } from "@/components/ui/motion";

const DESKTOP_LINKS = [
  { href: "/app", label: "Home", icon: Home, exact: true },
  { href: "/app/spaces", label: "Spaces", icon: FolderHeart },
  { href: "/app/studio", label: "AI Studio", icon: Sparkles },
  { href: "/app/account", label: "Account", icon: User },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen pb-24 md:pb-12">
      <header className="glass-nav sticky top-0 z-40">
        <div className="site-frame flex h-16 items-center justify-between gap-4">
          <Link href="/app" className="group inline-flex items-center">
            <BrandMark size="sm" className="sm:hidden" />
            <BrandMark size="md" className="hidden sm:inline-flex" />
          </Link>

          <nav aria-label="App navigation" className="hidden items-center gap-1 md:flex">
            {DESKTOP_LINKS.map((item) => {
              const Icon = item.icon;
              const active = item.exact
                ? pathname === item.href
                : pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`relative inline-flex min-h-[38px] items-center gap-1.5 rounded-full px-3.5 text-sm font-medium transition-colors ${
                    active
                      ? "text-[var(--primary-foreground)]"
                      : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  }`}
                >
                  {active && (
                    <motion.span
                      layoutId="app-desktop-nav"
                      transition={{ type: "spring", stiffness: 420, damping: 32 }}
                      className="absolute inset-0 rounded-full bg-[var(--primary)] shadow-sm"
                    />
                  )}
                  <span className="relative z-10 inline-flex items-center gap-1.5">
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </span>
                </Link>
              );
            })}
          </nav>

          <Link
            href="/app/create"
            className="inline-flex min-h-[40px] items-center gap-1.5 rounded-full bg-[var(--primary)] px-4 text-sm font-medium text-[var(--primary-foreground)] shadow-sm transition-all duration-200 hover:brightness-110 hover:shadow-md active:scale-[0.97]"
          >
            <Plus className="h-4 w-4" />
            <span className="hidden sm:inline">New space</span>
            <span className="sm:hidden">New</span>
          </Link>
        </div>
      </header>

      <main className="site-frame py-8 sm:py-10">{children}</main>

      <MobileBottomNav tabs={APP_BOTTOM_TABS} />
    </div>
  );
}
