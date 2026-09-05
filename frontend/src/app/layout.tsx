import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Talevora — Agentic Screenwriting Studio",
  description: "Talevora: Multi-agent AI studio for collaborative screenwriting — from pitch to performable script",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
