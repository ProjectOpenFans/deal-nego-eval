import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "谈判评测控制台",
  description:
    "可交互查看谈判历史、初始输入、评分结果与完整运行参数。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
