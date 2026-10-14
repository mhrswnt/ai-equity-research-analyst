import type { Metadata } from "next";
import "./globals.css";
import { AppProvider } from "@/lib/store";
import { Shell } from "@/components/Shell";

export const metadata: Metadata = { title: "Equity Research Assistant", description: "AI equity research for Indian markets" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <body>
        <AppProvider><Shell>{children}</Shell></AppProvider>
      </body>
    </html>
  );
}
