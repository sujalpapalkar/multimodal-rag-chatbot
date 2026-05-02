import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DocMind — Multimodal RAG Chatbot",
  description: "Ask questions about your PDF documents with AI-powered search",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
