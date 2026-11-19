import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import type { ScanListItem } from '../api/scans'
import { useAllScans, useDeleteScan, useNeedsReview } from '../features/scans/queries'
import { ScanTable } from '../features/scans/ScanTable'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { EmptyState } from '../ui/EmptyState'
import { Skeleton, useDelayed } from '../ui/Skeleton'
import { useToast } from '../ui/Toast'

// S2 (DESIGN 12, PRD 12): "Needs review" first, then newest first.
export function Scans() {
  const navigate = useNavigate()
  const toast = useToast()
  const review = useNeedsReview()
  const all = useAllScans()
  const del = useDeleteScan()
  const [toDelete, setToDelete] = useState<ScanListItem | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const showSkeleton = useDelayed()

  useEffect(() => {
    document.title = 'Scans · Privacy Guardian'
  }, [])

  const scans = useMemo(() => {
    const waiting = review.data?.items ?? []
    const ids = new Set(waiting.map((s) => s.id))
    const rest = (all.data?.pages ?? []).flatMap((p) => p.items).filter((s) => !ids.has(s.id))
    return [...waiting, ...rest]
  }, [review.data, all.data])

  const loading = review.isPending || all.isPending
  const failed = review.isError || all.isError

  function confirmDelete() {
    if (!toDelete) return
    const name = toDelete.filename
    del.mutate(toDelete.id, {
      onSuccess: () => {
        setToDelete(null)
        toast(`Deleted ${name}`)
      },
      onError: (e) => {
        setToDelete(null)
        setDeleteError(
          e instanceof ApiError && e.code === 'scan_running'
            ? `${name} is still running. Delete it when it has finished.`
            : `Could not delete ${name}. Try again.`,
        )
      },
    })
  }

  return (
    <section aria-labelledby="page-title" className="flex flex-col gap-8">
      <header className="flex items-center justify-between gap-4 flex-wrap">
        <h1 id="page-title" className="heading-5">
          Scans
        </h1>
        <Button onClick={() => navigate('/scans/new')}>New scan</Button>
      </header>

      {deleteError && <Banner tone="error">{deleteError}</Banner>}

      <div className="rounded-lg border border-rule bg-paper px-3 sm:px-0">
        {failed ? (
          <div className="flex flex-col items-start gap-3 p-6">
            <Banner tone="error">Could not load scans.</Banner>
            <Button
              variant="text"
              onClick={() => {
                void review.refetch()
                void all.refetch()
              }}
            >
              Retry
            </Button>
          </div>
        ) : loading ? (
          <div aria-busy="true" aria-label="Loading scans" className="flex flex-col gap-4 p-6">
            {showSkeleton &&
              [0, 1, 2].map((i) => (
                <div key={i} className="flex gap-6">
                  <Skeleton className="h-4 w-1/3" />
                  <Skeleton className="h-4 w-1/6" />
                  <Skeleton className="h-4 w-1/6" />
                </div>
              ))}
          </div>
        ) : scans.length === 0 ? (
          <EmptyState
            text="No scans yet. Start your first scan."
            action={<Button onClick={() => navigate('/scans/new')}>New scan</Button>}
          />
        ) : (
          <ScanTable scans={scans} onDelete={(s) => (setDeleteError(null), setToDelete(s))} />
        )}
      </div>

      {all.hasNextPage && (
        <div>
          <Button
            variant="secondary"
            loading={all.isFetchingNextPage}
            loadingLabel="Loading more scans"
            onClick={() => void all.fetchNextPage()}
          >
            Load more scans
          </Button>
        </div>
      )}

      <Dialog
        open={toDelete !== null}
        title={`Delete ${toDelete?.filename ?? 'this scan'}?`}
        confirmLabel="Delete scan"
        confirmBusyLabel="Deleting scan"
        busy={del.isPending}
        danger
        onConfirm={confirmDelete}
        onClose={() => setToDelete(null)}
      >
        The original, the cleaned file and the report are removed now. This cannot be undone.
      </Dialog>
    </section>
  )
}
