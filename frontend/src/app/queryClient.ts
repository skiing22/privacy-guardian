import { QueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'

// ARCHITECTURE 13.1: retry GETs twice (never 4xx), never retry POSTs automatically.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) =>
        count < 2 && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
})
