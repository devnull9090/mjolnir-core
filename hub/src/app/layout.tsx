import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import GoogleAnalytics from "./components/GoogleAnalytics";
import { HubKitProvider } from "./components/HubKit";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "MJOLNIR Core — Halo Campaign Evolved Modding Platform",
  description:
    "The open-source modding framework and community platform for Halo Campaign Evolved. Download mods, share your creations, and join the community.",
  openGraph: {
    title: "MJOLNIR Core",
    description: "Modding platform for Halo Campaign Evolved",
    url: "https://mjolnircore.com",
    siteName: "MJOLNIR Core",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <GoogleAnalytics />
        {/* One identity lookup for the whole page: the navbar chip, the
            rating widget and the comment box all read the same session. */}
        <HubKitProvider>{children}</HubKitProvider>
      </body>
    </html>
  );
}
