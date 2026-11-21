import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { themeBootstrap } from "@/lib/theme";

export const metadata: Metadata = {
  title: { default: "NEXUS", template: "%s · NEXUS" },
  description: "Your personal AI operating system.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/icon.svg" },
  appleWebApp: { capable: true, title: "NEXUS", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  themeColor: "#0b0e16",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body className="min-h-dvh font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
