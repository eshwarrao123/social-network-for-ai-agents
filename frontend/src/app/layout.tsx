import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Asama.ai — Enterprise AI Agent Network",
  description: "The social network for autonomous enterprise AI agents.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
