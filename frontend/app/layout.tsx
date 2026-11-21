import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "RAGForge · Knowledge into answers",
  description: "Build, inspect and test grounded knowledge APIs.",
};
export default function Layout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
