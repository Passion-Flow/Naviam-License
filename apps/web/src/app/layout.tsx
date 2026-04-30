import "@/styles/globals.css";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "License Console",
  description: "厂商 License 签发与管理",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
