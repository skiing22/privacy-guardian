import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteScan, listScans, OPEN_STATUSES, scanKeys, type ScanList } from '../../api/scans'

const REFRESH_WHILE_OPEN_MS = 5000

function hasOpen(lists: ScanList[] | undefined): boolean {
  return !!lists?.some((l) => l.items.some((s) => OPEN_STATUSES.has(s.status)))
}

/** Scans waiting for answers: shown first (DESIGN 12 S2). */
export function useNeedsReview() {
  return useQuery({
    queryKey: scanKeys.list('needs_review'),
    queryFn: () => listScans({ status: 'needs_review', limit: 100 }),
  })
}

/** Everything, newest first, 50 at a time. Refreshes while a scan is still running. */
export function useAllScans() {
  return useInfiniteQuery({
    queryKey: scanKeys.list(),
    queryFn: ({ pageParam }) => listScans({ cursor: pageParam, limit: 50 }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    refetchInterval: (q) => (hasOpen(q.state.data?.pages) ? REFRESH_WHILE_OPEN_MS : false),
  })
}

export function useDeleteScan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteScan,
    onSettled: () => qc.invalidateQueries({ queryKey: scanKeys.all }),
  })
}
