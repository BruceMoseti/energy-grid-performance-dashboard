import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "GridPulse — Real-Time Energy Grid Performance",
  description:
    "Hourly demand, day-ahead forecast accuracy and load KPIs for U.S. balancing authorities.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
