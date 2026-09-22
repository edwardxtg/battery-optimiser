import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Battery Optimiser",
  description:
    "Optimise a grid-scale battery (BESS) for wholesale energy arbitrage against live GB prices.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB">
      <body>{children}</body>
    </html>
  );
}
