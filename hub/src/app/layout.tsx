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
  // What relative URLs in any page's metadata resolve against — without it
  // an og:image of "/api/v1/media/…" is emitted pointing at localhost.
  metadataBase: new URL("https://mjolnircore.com"),
  title: "MJOLNIR Core — Multiplayer Modding for Halo Campaign Evolved",
  description:
    "The multiplayer modding framework for Halo Campaign Evolved. Play classic Halo CE maps, create custom maps and content, and join the MJOLNIR community.",
  openGraph: {
    title: "MJOLNIR Core",
    description:
      "Classic Halo CE multiplayer, custom maps, and a community of creators. The open-source multiplayer modding framework for Halo Campaign Evolved.",
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
