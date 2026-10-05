import { redirect } from "next/navigation";

/** The match history's player search: /players?name=X opens X's page. */
export default async function PlayersPage({ searchParams }: { searchParams: Promise<{ name?: string }> }) {
  const name = (await searchParams).name?.trim().slice(0, 64);
  redirect(name ? `/players/${encodeURIComponent(name)}` : "/matches");
}
