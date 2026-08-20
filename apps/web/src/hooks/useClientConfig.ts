import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';

/** The wire shape of `GET /api/v1/config`. */
interface ClientConfigResponse {
  avatar_uploads: boolean;
}

export interface ClientConfig {
  /** True when `POST /auth/me/avatar` has somewhere to put the bytes (Batch 44). */
  avatarUploads: boolean;
}

/** Everything off — what an older API that has no `/config` route implies. */
const NONE: ClientConfig = { avatarUploads: false };

/**
 * What this deployment can do, read from `GET /api/v1/config`.
 *
 * Features here are provisioned per environment rather than built in, so the client has
 * to ask. Falling back to "off" on any error is the safe direction and also the correct
 * one during a deploy gap: Vercel ships this app from `main` on merge while the API
 * waits for `/ship-prod`, so for a while the route does not exist yet and a 404 must
 * read as "not available", not as a broken settings page.
 *
 * `staleTime` is a minute rather than zero — the answer changes when an environment
 * variable changes, which is rare, but not never, and a member who has just been told a
 * feature exists should not have to sign out to see it.
 */
export function useClientConfig(): ClientConfig {
  const { data } = useQuery({
    queryKey: ['client-config'],
    queryFn: async (): Promise<ClientConfig> => {
      const config = await apiFetch<ClientConfigResponse>('/api/v1/config');
      return { avatarUploads: config.avatar_uploads === true };
    },
    staleTime: 60_000,
    retry: false,
  });
  return data ?? NONE;
}
