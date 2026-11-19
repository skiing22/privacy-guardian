import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getScan, type ScanStatusOut } from '../../api/scan'
import { scanKeys } from '../../api/scans'

/**
 * ARCHITECTURE 4 / D6: poll every 1 s while queued or running, every 5 s while the tab is
 * hidden, and stop on needs_review, done or failed.
 */
export const POLL_MS = 1000
export const POLL_HIDDEN_MS = 5000

function useHidden(): boolean {
  const [hidden, setHidden] = useState(() => document.visibilityState === 'hidden')
  useEffect(() => {
    const on = () => setHidden(document.visibilityState === 'hidden')
    document.addEventListener('visibilitychange', on)
    return () => document.removeEventListener('visibilitychange', on)
  }, [])
  return hidden
}

export function isOpen(s: ScanStatusOut | undefined): boolean {
  return s?.status === 'queued' || s?.status === 'running'
}

export function useScanStatus(id: string) {
  const hidden = useHidden()
  return useQuery({
    queryKey: scanKeys.one(id),
    queryFn: () => getScan(id),
    refetchInterval: (q) => (isOpen(q.state.data) ? (hidden ? POLL_HIDDEN_MS : POLL_MS) : false),
    refetchIntervalInBackground: true,
  })
}
