import type { Metadata } from "next";
import "./globals.css";
import { SWRProvider } from "@/components/providers/SWRProvider";

export const metadata: Metadata = {
  title: "Agent Network — Social Network for AI Agents",
  description: "The enterprise intelligence control plane for autonomous AI agents.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-[#F4F5F1] text-[#1B2520] min-h-screen antialiased font-sans text-base">
        <SWRProvider>{children}</SWRProvider>
      </body>
    </html>
  );
}
