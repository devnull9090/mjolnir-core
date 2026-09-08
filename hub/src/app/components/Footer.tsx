import Link from "next/link";
import { DiscordIcon, GitHubIcon } from "./icons";

function MjolnirIcon({ className = "w-8 h-8" }: { className?: string }) {
  return (
    <img
      src="/logo-transparent.png"
      alt="MJOLNIR Core"
      className={`${className} object-contain`}
    />
  );
}

const columns: { title: string; links: { href: string; label: string; external?: boolean }[] }[] = [
  {
    title: "Product",
    links: [
      { href: "/download", label: "Download" },
      { href: "/mods", label: "Mods" },
      { href: "/tools", label: "Tools" },
      { href: "/changelog", label: "Changelog" },
    ],
  },
  {
    title: "Developers",
    links: [
      { href: "/docs", label: "Docs" },
      { href: "/docs/tags", label: "Tag Reference" },
      { href: "/docs/console", label: "Console Commands" },
      { href: "/docs/api", label: "API" },
      { href: "https://github.com/devnull9090/mjolnir-core", label: "Source", external: true },
    ],
  },
  {
    title: "Community",
    links: [
      { href: "https://discord.gg/9gxYZsByW9", label: "Discord", external: true },
      {
        href: "https://github.com/devnull9090/mjolnir-core/issues",
        label: "Issues",
        external: true,
      },
    ],
  },
];

export function Footer() {
  return (
    <footer className="border-t border-border px-6 py-12">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col gap-10 md:flex-row md:justify-between">
          <div className="max-w-xs">
            <div className="flex items-center gap-2">
              <MjolnirIcon />
              <span className="text-lg font-bold tracking-wide text-gold">MJOLNIR</span>
              <span className="text-xs text-text-muted font-medium">CORE</span>
            </div>
            <p className="mt-3 text-sm leading-6 text-text-dim">
              The open-source modding framework and community platform for Halo Campaign
              Evolved. MIT licensed, built in the open.
            </p>
            <div className="mt-4 flex items-center gap-4">
              <Link
                href="https://github.com/devnull9090/mjolnir-core"
                target="_blank"
                aria-label="GitHub"
                className="text-text-dim hover:text-foreground transition-colors"
              >
                <GitHubIcon className="w-5 h-5" />
              </Link>
              <Link
                href="https://discord.gg/9gxYZsByW9"
                target="_blank"
                aria-label="Discord"
                className="text-text-dim hover:text-foreground transition-colors"
              >
                <DiscordIcon className="w-5 h-5" />
              </Link>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-8 sm:grid-cols-3 md:gap-14">
            {columns.map((column) => (
              <div key={column.title}>
                <h3 className="text-xs font-bold uppercase tracking-wider text-text-dim">
                  {column.title}
                </h3>
                <ul className="mt-3 space-y-2">
                  {column.links.map((link) => (
                    <li key={link.label}>
                      <Link
                        href={link.href}
                        target={link.external ? "_blank" : undefined}
                        className="text-sm text-text-muted hover:text-foreground transition-colors"
                      >
                        {link.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <p className="mt-10 border-t border-border pt-6 text-xs text-text-dim">
          MJOLNIR Core is a community project and is not affiliated with Microsoft, 343
          Industries / Halo Studios, or the developers of Halo Campaign Evolved.
        </p>
      </div>
    </footer>
  );
}
