import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Battery Optimiser",
  description:
    "Optimise a home battery for stacked wholesale-arbitrage and grid-event earnings.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB">
      <body>{children}</body>
    </html>
  );
}
