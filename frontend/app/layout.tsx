import type { Metadata, Viewport } from "next";
import { DM_Sans, Playfair_Display } from "next/font/google";

import "./globals.css";

const playfair = Playfair_Display({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-display",
  display: "swap",
});

const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Memory Lane — Every shared memory, kept in one warm place",
  description:
    "A collaborative, emotional memory album platform for life's milestones. Frictionless for guests, curated by you, powered by AI Memory Studio.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

/**
 * Synchronous FOUC-prevention script per `dark-mode-toggle` guidance:
 * Reads stored "light" | "dark" override from localStorage before first paint
 * and updates `<meta name="color-scheme">` + `data-theme`.
 */
const THEME_BOOTSTRAP_SCRIPT = `try{var s=localStorage.getItem("color-scheme");var m=document.querySelector('meta[name="color-scheme"]');if(s==="light"||s==="dark"){if(m)m.content=s;document.documentElement.dataset.theme=s;}else{if(m)m.content="light dark";delete document.documentElement.dataset.theme;}}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${playfair.variable} ${dmSans.variable}`}
    >
      <head>
        <meta name="color-scheme" content="light dark" />
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP_SCRIPT }} />
      </head>
      <body className="min-h-screen bg-[var(--background)] font-sans text-[var(--foreground)] antialiased selection:bg-[var(--sage)] selection:text-[var(--foreground)]">
        {children}
      </body>
    </html>
  );
}
