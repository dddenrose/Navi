import { useEffect, useState } from "react";
import { auth } from "@/lib/firebase";

/**
 * Read Firebase ID Token custom claims (e.g. admin, tier).
 * Updates when auth state changes or token refreshes.
 */
export function useTokenClaims() {
  const [claims, setClaims] = useState<{
    admin: boolean;
    tier: string | null;
    loaded: boolean;
  }>({ admin: false, tier: null, loaded: false });

  useEffect(() => {
    const unsubscribe = auth.onIdTokenChanged(async (user) => {
      if (!user) {
        setClaims({ admin: false, tier: null, loaded: true });
        return;
      }
      try {
        const result = await user.getIdTokenResult();
        setClaims({
          admin: result.claims.admin === true,
          tier: (result.claims.tier as string | undefined) ?? null,
          loaded: true,
        });
      } catch {
        setClaims({ admin: false, tier: null, loaded: true });
      }
    });
    return unsubscribe;
  }, []);

  return claims;
}
