import { Check, WarningCircle } from '@phosphor-icons/react'
import type { ScanStatusOut } from '../../api/scan'
import { STEPS } from './words'

/**
 * DESIGN 5.7: a real sequence, so numbered. Done steps get a tick, the current one an ink
 * blue dot, a failed one turns red with the error under it. One polite live region says
 * where the scan is ("Step 3 of 5, combining results").
 */
type Props = { scan: ScanStatusOut; preparingModel: boolean }

function label(i: number, scan: ScanStatusOut): string {
  const name = STEPS[i] ?? ''
  if (i === 4 && scan.round > 1) return `${name}, round ${scan.round} of ${scan.max_rounds}`
  return name
}

export function Progress({ scan, preparingModel }: Props) {
  const failed = scan.status === 'failed'
  const current = scan.status === 'queued' ? 0 : scan.step // 1-based; 0 = not started
  const announce =
    scan.status === 'queued'
      ? preparingModel
        ? 'Preparing the model'
        : 'Waiting to start'
      : `Step ${current} of 5, ${label(current - 1, scan).toLowerCase()}`

  return (
    <div className="flex flex-col gap-4">
      <p className="sr-only" aria-live="polite">
        {announce}
      </p>
      {scan.status === 'queued' && (
        <p className="body-6 text-ink-muted">
          {preparingModel
            ? 'Preparing the model, about 30 seconds, only the first time.'
            : 'Waiting to start.'}
        </p>
      )}
      <ol aria-label="Progress" className="flex flex-col gap-3">
        {STEPS.map((_, i) => {
          const n = i + 1
          const state =
            failed && n === current
              ? 'failed'
              : n < current || scan.status === 'done'
                ? 'done'
                : n === current && scan.status !== 'queued'
                  ? 'current'
                  : 'todo'
          return (
            <li key={n} className="flex items-start gap-3">
              <span
                aria-hidden
                className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center"
              >
                {state === 'done' && <Check size={16} weight="bold" className="text-sign" />}
                {state === 'current' && <span className="h-2.5 w-2.5 rounded-full bg-sign" />}
                {state === 'failed' && (
                  <WarningCircle size={18} weight="bold" className="text-risk-high" />
                )}
              </span>
              <span
                aria-hidden
                className={`mt-0.5 w-4 shrink-0 tabular-nums body-6 ${state === 'todo' ? 'text-ink-muted' : 'text-ink'}`}
              >
                {n}
              </span>
              <div className="flex flex-col gap-1">
                <span
                  className={
                    state === 'current'
                      ? 'title-3 text-ink'
                      : state === 'failed'
                        ? 'title-3 text-risk-high'
                        : state === 'done'
                          ? 'body-3 text-ink'
                          : 'body-3 text-ink-muted'
                  }
                >
                  <span className="sr-only">
                    {state === 'done'
                      ? 'Done: '
                      : state === 'current'
                        ? 'Now: '
                        : state === 'failed'
                          ? 'Failed: '
                          : ''}
                  </span>
                  {label(i, scan)}
                </span>
                {state === 'failed' && scan.error && (
                  <span className="body-6 text-risk-high">{scan.error.message}</span>
                )}
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
