"use client";
import localFont from "next/font/local";
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "../contexts/AuthContext";
import { AgentProvider } from "../contexts/AgentContextDynamic";
import { Layout } from "../components/Layout";
import { Toaster } from "react-hot-toast";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { usePathname } from "next/navigation";
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const fontBrandRegular = localFont({
  src: "./fonts/AspektaVF.woff2",
  variable: "--font-brand-regular",
  display: "swap",
  style: "normal",
  weight: "100 900",
  preload: true,
  fallback: ["sans-serif"],
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000, // 1 minute
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  const pathname = usePathname();
  const isLoginPage = pathname === "/login";
  const isManagerPage = pathname?.startsWith("/manager");
  const shouldUseLayout = !isLoginPage && !isManagerPage;

  return (
    <html lang="en">
      <body
        className={` ${fontBrandRegular.className} ${geistMono.variable} antialiased`}>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <AgentProvider>
              {shouldUseLayout ? <Layout>{children}</Layout> : children}
              <Toaster position="top-right" />
            </AgentProvider>
          </AuthProvider>
        </QueryClientProvider>
      </body>
    </html>
  );
}
