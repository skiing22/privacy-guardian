import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { downloadUrl, getHealth, getResult, retryScan } from '../api/scan'
import { scanKeys } from '../api/scans'
import { ReviewPanel } from '../features/review/ReviewPanel'
import { Progress } from '../features/scan/Progress'
import { ResultView } from '../features/scan/ResultView'
import { RiskBanner } from '../features/scan/RiskBanner'
import { isOpen, useScanStatus } from '../features/scan/useScanStatus'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Skeleton, useDelayed } from '../ui/Skeleton'

/**
 * S4 (D7): run, review and result on one page. This part (P15) covers running, paused and
 * failed; the done state shows the risk and downloads until the result sheet (P16) lands.
 */
export function Scan() {
  const { id = '' } = useParams()
  const qc = useQueryClient()
  const status = useScanStatus(id)
  const scan = status.data
  const showSkeleton = useDelayed()

  // "Preparing the model" only when the server says the model is not loaded yet.
  const health = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    enabled: scan?.status === 'queued',
    refetchInterval: (q) => (q.state.data?.model_ready === false ? 2000 : false),
  })

  const result = useQuery({
    queryKey: [...scanKeys.one(id), 'result'],
    queryFn: () => getResult(id),
    enabled: scan?.status === 'done',
    staleTime: Infinity, // a finished scan never changes
  })

  // DESIGN 9: the redaction pass plays once, and only if the scan finished while the user
  // was watching this page; opening a scan that was already done shows the result at once.
  const [pass, setPass] = useState<'idle' | 'armed' | 'played'>('idle')
  const status_ = scan?.status
  // React's "adjust state while rendering" pattern: runs once, when we first see it running.
  if (pass === 'idle' && status_ && status_ !== 'done') setPass('armed')
  useEffect(() => {
    if (pass !== 'armed' || status_ !== 'done' || !result.data) return
    const t = setTimeout(() => setPass('played'), 1600) // 1.5 s cap + a frame
    return () => clearTimeout(t)
  }, [pass, status_, result.data])
  const animate = status_ === 'done' && pass === 'armed'

  const retry = useMutation({
    mutationFn: () => retryScan(id),
    onSettled: () => qc.invalidateQueries({ queryKey: scanKeys.one(id) }),
  })

  useEffect(() => {
    document.title = `${scan?.filename ?? 'Scan'} · Privacy Guardian`
  }, [scan?.filename])

  if (status.isError) {
    const gone = status.error instanceof ApiError && status.error.status === 404
    return (
      <section aria-labelledby="page-title" className="flex flex-col gap-4">
        <h1 id="page-title" className="heading-5">
          {gone ? 'This scan does not exist.' : 'Could not load this scan.'}
        </h1>
        {gone ? (
          <p className="body-3 text-ink-muted">
            It may have been deleted, or it expired after 7 days.
          </p>
        ) : (
          <Button variant="text" className="self-start" onClick={() => void status.refetch()}>
            Retry
          </Button>
        )}
        <Link to="/scans" className="body-3 text-sign hover:underline">
          Go to your scans
        </Link>
      </section>
    )
  }

  if (!scan) {
    return (
      <div aria-busy="true" aria-label="Loading scan" className="flex flex-col gap-4">
        {showSkeleton && (
          <>
            <Skeleton className="h-6 w-64" />
            <Skeleton className="h-40 w-full max-w-[680px]" />
          </>
        )}
      </div>
    )
  }

  const pdf = scan.format === 'pdf'

  return (
    <section aria-labelledby="page-title" className="flex flex-col gap-8">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex flex-col gap-1 min-w-0">
          <nav aria-label="Breadcrumb" className="body-6 text-ink-muted">
            <Link to="/scans" className="text-sign hover:underline">
              Scans
            </Link>{' '}
            / <span aria-current="page">{scan.filename}</span>
          </nav>
          <h1 id="page-title" className="heading-5 break-all">
            {scan.filename}
          </h1>
        </div>
        {scan.status === 'done' && (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
            <a
              href={downloadUrl(id, 'cleaned')}
              className="inline-flex h-10 pointer-coarse:min-h-11 items-center justify-center rounded-md bg-sign px-3 button-md text-white hover:bg-sign-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sign"
            >
              {pdf ? 'Download cleaned text (.txt)' : 'Download cleaned file'}
            </a>
            <a
              href={downloadUrl(id, 'report')}
              className="inline-flex h-10 pointer-coarse:min-h-11 items-center justify-center rounded-md border border-rule-strong bg-paper px-3 button-md text-ink hover:bg-desk focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sign"
            >
              Download report
            </a>
          </div>
        )}
      </header>

      {scan.status === 'done' && pdf && (
        <p className="body-6 text-ink-muted -mt-6">PDFs are returned as text.</p>
      )}

      {scan.status === 'done' && scan.risk && <RiskBanner risk={scan.risk} />}

      {scan.status === 'failed' && (
        <div className="flex flex-col items-start gap-3">
          <Banner tone="error">
            Scan failed at step {scan.error?.step ?? scan.step}. {scan.error?.message}
          </Banner>
          <Button
            variant="secondary"
            loading={retry.isPending}
            loadingLabel="Retrying scan"
            onClick={() => retry.mutate()}
          >
            Retry scan
          </Button>
        </div>
      )}

      {scan.status === 'needs_review' && scan.review && scan.review.items.length > 0 ? (
        <div className="max-w-[760px]">
          <ReviewPanel key={scan.updated_at} scanId={id} items={scan.review.items} />
        </div>
      ) : (
        (isOpen(scan) || scan.status === 'failed') && (
          <div className="rounded-lg border border-rule bg-paper p-6 max-w-[480px]">
            <Progress scan={scan} preparingModel={health.data?.model_ready === false} />
          </div>
        )
      )}

      {scan.status === 'done' &&
        (result.data ? (
          <ResultView result={result.data} animate={animate} />
        ) : result.isError ? (
          <div className="flex flex-col items-start gap-3">
            <Banner tone="error">Could not load the result.</Banner>
            <Button variant="text" onClick={() => void result.refetch()}>
              Retry
            </Button>
          </div>
        ) : (
          <div aria-busy="true" aria-label="Loading result" className="flex flex-col gap-3">
            {showSkeleton && <Skeleton className="h-64 w-full max-w-[776px]" />}
          </div>
        ))}

      {scan.status === 'done' && (
        <p className="body-6 text-ink-muted">
          Checked for leaks in {scan.round} {scan.round === 1 ? 'round' : 'rounds'}.
        </p>
      )}
    </section>
  )
}
