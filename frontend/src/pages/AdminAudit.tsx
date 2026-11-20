import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import {
  adminKeys,
  auditPage,
  saveAnchor,
  verifyLog,
  type AnchorOut,
  type VerifyOut,
} from '../api/admin'
import { badRow, details, verifySentence } from '../features/admin/words'
import { formatStarted } from '../lib/format'
import { prefersReducedMotion } from '../lib/useMediaQuery'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { EmptyState } from '../ui/EmptyState'
import { Skeleton, useDelayed } from '../ui/Skeleton'

// S6 (DESIGN 12): newest first; Verify log checks the whole chain and the saved anchor.
const MAX_PAGES_TO_FIND_ROW = 20

export function AdminAudit() {
  const qc = useQueryClient()
  const showSkeleton = useDelayed()
  const [verified, setVerified] = useState<VerifyOut | null>(null)
  const [anchor, setAnchor] = useState<AnchorOut | null>(null)

  const log = useInfiniteQuery({
    queryKey: adminKeys.audit,
    queryFn: ({ pageParam }) => auditPage(pageParam),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.next_before_seq,
  })
  const rows = useMemo(() => (log.data?.pages ?? []).flatMap((p) => p.items), [log.data])

  useEffect(() => {
    document.title = 'Audit log · Privacy Guardian'
  }, [])

  const verify = useMutation({
    mutationFn: verifyLog,
    onSuccess: (v) => {
      setVerified(v)
      setAnchor(null)
    },
  })
  const save = useMutation({
    mutationFn: saveAnchor,
    onSuccess: (a) => {
      setAnchor(a)
      setVerified(null)
      void qc.invalidateQueries({ queryKey: adminKeys.audit })
    },
  })

  // Tampered row: load older pages until it is on screen, then outline and scroll to it.
  const bad = badRow(verified ?? undefined)
  useEffect(() => {
    if (bad === null || !log.data) return
    const loaded = rows.some((r) => r.seq === bad)
    if (!loaded && log.hasNextPage && log.data.pages.length < MAX_PAGES_TO_FIND_ROW) {
      void log.fetchNextPage()
      return
    }
    document
      .getElementById(`audit-${bad}`)
      ?.scrollIntoView?.({ block: 'center', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
  }, [bad, rows, log])

  const anchorTime = verified?.anchor ? formatStarted(verified.anchor.saved_at) : undefined

  return (
    <section aria-labelledby="page-title" className="flex flex-col gap-8">
      <header className="flex items-center justify-between gap-4 flex-wrap">
        <h1 id="page-title" className="heading-5">
          Audit log
        </h1>
        <div className="flex gap-2 flex-wrap">
          <Button
            variant="secondary"
            loading={save.isPending}
            loadingLabel="Saving anchor"
            onClick={() => save.mutate()}
          >
            Save anchor
          </Button>
          <Button
            loading={verify.isPending}
            loadingLabel="Verifying log"
            onClick={() => verify.mutate()}
          >
            Verify log
          </Button>
        </div>
      </header>

      <div aria-live="assertive" className="flex flex-col gap-2 empty:hidden">
        {verified && (
          <Banner tone={verified.ok ? 'success' : 'error'}>
            {verifySentence(verified, anchorTime)}
          </Banner>
        )}
        {anchor && (
          <Banner tone="info">
            Anchor saved at record {anchor.seq}. Write down this code and keep it off this server:{' '}
            <span className="font-mono">{anchor.mac_prefix}</span>
          </Banner>
        )}
        {(verify.isError || save.isError) && (
          <Banner tone="error">Could not reach the audit log. Try again.</Banner>
        )}
      </div>

      <div className="rounded-lg border border-rule bg-paper px-3 sm:px-0">
        {log.isError ? (
          <div className="flex flex-col items-start gap-3 p-6">
            <Banner tone="error">Could not load the audit log.</Banner>
            <Button variant="text" onClick={() => void log.refetch()}>
              Retry
            </Button>
          </div>
        ) : !log.data ? (
          <div aria-busy="true" aria-label="Loading audit log" className="flex flex-col gap-4 p-6">
            {showSkeleton && [0, 1, 2].map((i) => <Skeleton key={i} className="h-4 w-full" />)}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState text="No events yet." />
        ) : (
          <table className="w-full border-collapse tabular-nums">
            <thead className="hidden sm:table-header-group">
              <tr className="border-b border-rule">
                {['#', 'Time', 'Who', 'Event', 'Details'].map((h) => (
                  <th
                    key={h}
                    scope="col"
                    className="title-4 text-ink-muted text-left font-medium px-3 py-2"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const tampered = r.seq === bad
                return (
                  <tr
                    key={r.seq}
                    id={`audit-${r.seq}`}
                    aria-label={
                      tampered ? `Record ${r.seq}, changed after it was saved` : undefined
                    }
                    className={[
                      'flex flex-col sm:table-row border-b border-rule last:border-b-0 py-2 sm:py-0 scroll-mt-28',
                      tampered
                        ? 'outline-2 -outline-offset-2 outline-risk-high bg-risk-high-bg'
                        : '',
                    ].join(' ')}
                  >
                    <td className="px-3 sm:h-11 body-6 text-ink-muted">
                      <span className="sm:hidden">Record </span>
                      {r.seq}
                    </td>
                    <td className="px-3 body-6 text-ink-muted whitespace-nowrap">
                      {formatStarted(r.ts)}
                    </td>
                    <td className="px-3 body-6 text-ink break-all">
                      {r.actor.type === 'system'
                        ? 'System'
                        : (r.actor.email ?? `user ${r.actor.id ?? ''}`)}
                    </td>
                    <td className="px-3 body-6 text-ink">{r.event_label}</td>
                    <td className="px-3 body-6 text-ink-muted break-words">
                      {details(r).map((d, i) =>
                        d.mono ? (
                          <span key={i} className="font-mono text-ink">
                            {d.text}
                          </span>
                        ) : (
                          <span key={i}>{d.text}</span>
                        ),
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {log.hasNextPage && (
        <div>
          <Button
            variant="secondary"
            loading={log.isFetchingNextPage}
            loadingLabel="Loading older records"
            onClick={() => void log.fetchNextPage()}
          >
            Load older records
          </Button>
        </div>
      )}
    </section>
  )
}
