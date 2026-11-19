import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { isSessionError, SESSION_KEY, type Session } from '../api/auth'

/**
 * ARCHITECTURE 13.1: retry GETs twice (never 4xx), never retry POSTs automatically.
 * ARCHITECTURE 4: a 401 anywhere ends the session in the app; the auth guard then sends
 * the user to /login?next=... with "Please log in again" (PRD 12).
 */
export function createQueryClient(): QueryClient {
  const onError = (error: unknown) => {
    if (!isSessionError(error)) return
    const now = client.getQueryData<Session>(SESSION_KEY)
    if (!now?.user) return // already logged out: nothing to end
    // Drop everything the old session loaded (other user's data on a shared computer).
    client.removeQueries({ predicate: (q) => q.queryKey[0] !== SESSION_KEY[0] })
    client.setQueryData<Session>(SESSION_KEY, { user: null, ended: true })
  }
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: {
      queries: {
        retry: (count, error) =>
          count < 2 && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  })
  return client
}

export const queryClient = createQueryClient()
