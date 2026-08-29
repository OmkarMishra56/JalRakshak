import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AquaAlert — Live Waterlogging Map",
  description: "Real-time, crowd-sourced flood risk for every ward in the city.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-body min-h-screen">{children}</body>
    </html>
  );
}
