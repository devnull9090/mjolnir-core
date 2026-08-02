/**
 * What every shared component needs from the app hosting it: a client to
 * call the API with, who the caller is, and how this particular app asks
 * someone to sign in.
 *
 * The website answers "sign in" by navigating to Discord OAuth; the launcher
 * answers it by starting a device pairing and opening a browser. Neither
 * detail belongs inside a rating widget, so both arrive through here.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { HubClient } from "../client";
import type { User } from "../types";

export interface HubContextValue {
  client: HubClient;
  /** null while loading is indistinguishable from signed out on purpose: a
   *  component should render its signed-out state until proven otherwise. */
  user: User | null;
  /** False until the first /auth/me answer lands. */
  ready: boolean;
  refreshUser: () => void;
  signIn: () => void;
  signOut: () => void;
  /** Opens a URL the way this app opens URLs (system browser in Tauri). */
  openUrl: (url: string) => void;
}

const HubContext = createContext<HubContextValue | null>(null);

export interface HubProviderProps {
  client: HubClient;
  children: ReactNode;
  /** Defaults to sending the browser to Discord OAuth. */
  onSignIn?: () => void;
  /** Drops whatever credential this host holds; the context re-checks after. */
  onSignOut?: () => void | Promise<void>;
  /** Defaults to `window.open`; the launcher routes to the system browser. */
  onOpenUrl?: (url: string) => void;
  /** Skips the initial /auth/me call for surfaces that never write. */
  anonymous?: boolean;
}

export function HubProvider({
  client,
  children,
  onSignIn,
  onSignOut,
  onOpenUrl,
  anonymous = false,
}: HubProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(anonymous);

  const refreshUser = useCallback(() => {
    if (anonymous) return;
    client
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true));
  }, [client, anonymous]);

  useEffect(refreshUser, [refreshUser]);

  const openUrl = useCallback(
    (url: string) => {
      if (onOpenUrl) onOpenUrl(url);
      else if (typeof window !== "undefined") window.open(url, "_blank", "noopener");
    },
    [onOpenUrl],
  );

  const value = useMemo<HubContextValue>(
    () => ({
      client,
      user,
      ready,
      refreshUser,
      openUrl,
      signIn:
        onSignIn ??
        (() => {
          if (typeof window !== "undefined") {
            window.location.href = client.signInUrl(
              window.location.pathname + window.location.search,
            );
          }
        }),
      // Whatever the host does to sign out — clear a cookie, forget a paired
      // key — the context ends up asking the API again, so a failed sign-out
      // cannot leave a stale identity on screen.
      signOut: () => {
        Promise.resolve(onSignOut ? onSignOut() : client.logout())
          .catch(() => {})
          .finally(() => {
            setUser(null);
            refreshUser();
          });
      },
    }),
    [client, user, ready, refreshUser, openUrl, onSignIn, onSignOut],
  );

  return <HubContext.Provider value={value}>{children}</HubContext.Provider>;
}

export function useHub(): HubContextValue {
  const ctx = useContext(HubContext);
  if (!ctx) {
    throw new Error("useHub must be used inside a <HubProvider>");
  }
  return ctx;
}
