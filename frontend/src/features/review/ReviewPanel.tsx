import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { sendAnswers, type ReviewItem, type Verdict } from '../../api/scan'
import { scanKeys } from '../../api/scans'
import { Banner } from '../../ui/Banner'
import { Button } from '../../ui/Button'
import { typeName } from '../../ui/TypeLabel'
import { Mark } from '../scan/Mark'
import { reasonWords } from '../scan/words'
import { clearAnswers, loadAnswers, saveAnswers } from './answersStore'
import { ignoreKey } from './keys'

/**
 * DESIGN 5.6 review card + keyboard (DESIGN 9): 1 2 3 answer, ↑ ↓ move, Z undoes the last
 * answer within 5 s. Answering moves to the next unanswered item. "Submit answers" appears
 * only when every item has an answer.
 */
const VERDICTS: { v: Verdict; key: string; label: string }[] = [
  { v: 'protect', key: '1', label: 'Protect' },
  { v: 'keep', key: '2', label: 'Keep visible' },
  { v: 'not_pii', key: '3', label: 'Not personal data' },
]
const VERDICT_WORD: Record<Verdict, string> = {
  protect: 'Protect',
  keep: 'Keep visible',
  not_pii: 'Not personal data',
}
const UNDO_MS = 5000
// API 4.7: the server sends at most 60 characters each side; exactly 60 means it was cut.
const CONTEXT_CHARS = 60

type Props = { scanId: string; items: ReviewItem[] }

export function ReviewPanel({ scanId, items }: Props) {
  const qc = useQueryClient()
  const [answers, setAnswers] = useState<Record<number, Verdict>>(() => {
    const saved = loadAnswers(scanId)
    const valid = new Set(items.map((i) => i.index))
    return Object.fromEntries(Object.entries(saved).filter(([k]) => valid.has(Number(k))))
  })
  const [pos, setPos] = useState(() => {
    const first = items.findIndex((i) => !(i.index in loadAnswers(scanId)))
    return first === -1 ? 0 : first
  })
  const [undo, setUndo] = useState<{ index: number; pos: number } | null>(null)
  const [undoPaused, setUndoPaused] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submitRef = useRef<HTMLButtonElement>(null)

  const item = items[pos]
  const done = items.every((i) => i.index in answers)
  const answeredCount = items.filter((i) => i.index in answers).length

  useEffect(() => saveAnswers(scanId, answers), [scanId, answers])

  useEffect(() => {
    if (!undo || undoPaused) return
    const t = setTimeout(() => setUndo(null), UNDO_MS)
    return () => clearTimeout(t)
  }, [undo, undoPaused])

  const submit = useMutation({
    mutationFn: () =>
      sendAnswers(
        scanId,
        items.map((i) => ({ index: i.index, verdict: answers[i.index] as Verdict })),
      ),
    onSuccess: () => {
      clearAnswers(scanId)
      void qc.invalidateQueries({ queryKey: scanKeys.all })
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === 'not_waiting_for_review') {
        clearAnswers(scanId) // already accepted (API 4.8 idempotency): the scan moved on
        void qc.invalidateQueries({ queryKey: scanKeys.one(scanId) })
        return
      }
      if (e instanceof ApiError && (e.code === 'auth_required' || e.code === 'session_expired'))
        return // answers are saved; the login page takes over and brings the user back
      setError('Your answers could not be saved. Retry.')
    },
  })

  const answer = useCallback(
    (v: Verdict) => {
      if (!item || submit.isPending) return
      setError(null)
      const next = { ...answers, [item.index]: v }
      setAnswers(next)
      setUndo({ index: item.index, pos })
      const after = items.findIndex((i, k) => k > pos && !(i.index in next))
      const before = items.findIndex((i) => !(i.index in next))
      const to = after !== -1 ? after : before
      if (to !== -1) setPos(to)
    },
    [item, answers, items, pos, submit.isPending],
  )

  const undoLast = useCallback(() => {
    if (!undo) return
    setAnswers((a) =>
      Object.fromEntries(Object.entries(a).filter(([k]) => Number(k) !== undo.index)),
    )
    setPos(undo.pos)
    setUndo(null)
  }, [undo])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (ignoreKey(e)) return
      const v = VERDICTS.find((x) => x.key === e.key)
      if (v) answer(v.v)
      else if (e.key === 'ArrowDown') setPos((p) => Math.min(items.length - 1, p + 1))
      else if (e.key === 'ArrowUp') setPos((p) => Math.max(0, p - 1))
      else if (e.key === 'z' || e.key === 'Z') undoLast()
      else return
      e.preventDefault()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [answer, undoLast, items.length])

  useEffect(() => {
    if (done) submitRef.current?.focus()
  }, [done])

  const announce = useMemo(
    () =>
      item
        ? `Item ${pos + 1} of ${items.length}, ${typeName(item.pii_type).toLowerCase()}, ${Math.round(item.score * 100)}% sure`
        : '',
    [item, pos, items.length],
  )

  if (!item) return null
  const ctx = item.context
  const name = typeName(item.pii_type)

  return (
    <section aria-labelledby="review-title" className="flex flex-col gap-4">
      <h2 id="review-title" className="title-3 text-ink">
        Needs your answer: {pos + 1} of {items.length}
      </h2>
      <p className="sr-only" aria-live="polite">
        {announce}
      </p>

      <div className="rounded-lg border border-rule bg-paper p-6 flex flex-col gap-6">
        <p className="body-7 text-ink break-words">
          {ctx.before.length >= CONTEXT_CHARS && '…'}
          {ctx.before}
          <Mark family={item.family} label={`${name}, needs your answer`}>
            {ctx.text}
          </Mark>
          {ctx.after}
          {ctx.after.length >= CONTEXT_CHARS && '…'}
        </p>
        <div className="flex flex-col gap-1">
          <p className="title-3 text-ink">
            Is this personal data? {name}, {Math.round(item.score * 100)}% sure.
          </p>
          <p className="body-6 text-ink-muted">{reasonWords(item.reason)}</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2" role="group" aria-label="Answer">
          {VERDICTS.map(({ v, key, label }) => {
            const chosen = answers[item.index] === v
            return (
              <Button key={v} variant="secondary" aria-pressed={chosen} onClick={() => answer(v)}>
                <kbd className="caption-4 rounded-sm border border-rule px-1 text-ink-muted font-sans">
                  {key}
                </kbd>
                {label}
              </Button>
            )
          })}
        </div>
      </div>

      <div className="flex items-center gap-4 min-h-10 flex-wrap">
        {undo && (
          <span
            className="flex items-center gap-2 body-6 text-ink-muted"
            onMouseEnter={() => setUndoPaused(true)}
            onMouseLeave={() => setUndoPaused(false)}
            onFocus={() => setUndoPaused(true)}
            onBlur={() => setUndoPaused(false)}
          >
            Answer saved.
            <Button variant="text" onClick={undoLast}>
              Undo
            </Button>
          </span>
        )}
        <span className="body-6 text-ink-muted ml-auto tabular-nums">
          {answeredCount} of {items.length} answered
        </span>
      </div>

      {error && <Banner tone="error">{error}</Banner>}

      {done && (
        <div>
          <Button
            ref={submitRef}
            loading={submit.isPending}
            loadingLabel="Submitting answers"
            onClick={() => submit.mutate()}
          >
            Submit answers
          </Button>
        </div>
      )}

      <ol aria-label="Items to review" className="flex flex-col border-t border-rule">
        {items.map((it, k) => {
          const a = answers[it.index]
          return (
            <li key={it.index}>
              <button
                type="button"
                aria-current={k === pos ? 'true' : undefined}
                onClick={() => setPos(k)}
                className={[
                  'w-full text-left flex items-center gap-3 px-3 min-h-11 border-b border-rule body-6',
                  'transition-colors duration-200 ease-base hover:bg-desk',
                  'focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-sign',
                  k === pos ? 'bg-sign-soft' : '',
                ].join(' ')}
              >
                <span className="tabular-nums text-ink-muted w-6">{k + 1}</span>
                <span className="flex-1 truncate text-ink">
                  {typeName(it.pii_type)}: {it.context.text}
                </span>
                <span className={a ? 'text-ink' : 'text-ink-muted'}>
                  {a ? VERDICT_WORD[a] : 'No answer yet'}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
      <p className="caption-2 text-ink-muted">
        Keys: 1 Protect, 2 Keep visible, 3 Not personal data, ↑ ↓ move, Z undo.
      </p>
    </section>
  )
}
