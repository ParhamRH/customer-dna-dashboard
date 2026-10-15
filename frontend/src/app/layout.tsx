import type { Metadata, Viewport } from "next";
import "@fontsource-variable/schibsted-grotesk";
import "@fontsource-variable/newsreader/opsz.css";
import "@fontsource-variable/newsreader/opsz-italic.css";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";
import { Providers } from "@/lib/providers";

export const metadata: Metadata = {
  title: { default: "Brand DNA", template: "%s · Brand DNA" },
  description: "Multi-tenant Brand DNA & Creative Intelligence Platform",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#f2f3f1", width: "device-width", initialScale: 1 };

const themeScript = `try{var t=localStorage.getItem('bdna-theme')||'system';var d=t==='dark'||(t==='system'&&matchMedia('(prefers-color-scheme: dark)').matches);if(d)document.documentElement.classList.add('dark');document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
