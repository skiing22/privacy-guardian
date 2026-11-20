import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { reveal } from '../../api/admin'
import { ApiError } from '../../api/client'
import { Banner } from '../../ui/Banner'
import { Button } from '../../ui/Button'
import { Dialog } from '../../ui/Dialog'
import { Field } from '../../ui/Field'
import { TextArea } from '../../ui/TextArea'

/**
 * DESIGN 7 "Show a real value": token + reason, then a confirm dialog, then the value in a
 * box with "Hide"; it hides itself after 60 s (paused while hovered or focused, DESIGN 11).
 * The value is kept ONLY in this component's state: not in the query cache, not in
 * storage, and it is cleared on hide and on leaving the page.
 */
const TOKEN = /^[A-Z_]+_[0-9a-f]{6,64}$/
const MIN_REASON = 10
const HIDE_AFTER_S = 60

type Shown = { token: string; value: string; logged: number | null }

export function RevealForm() {
  const [token, setToken] = useState('')
  const [reason, setReason] = useState('')
  const [tokenErr, setTokenErr] = useState<string | null>(null)
  const [reasonErr, setReasonErr] = useState<string | null>(null)
  const [formErr, setFormErr] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [shown, setShown] = useState<Shown | null>(null)
  const tokenRef = useRef<HTMLInputElement>(null)
  const reasonRef = useRef<HTMLTextAreaElement>(null)

  const hideValue = useCallback(() => setShown(null), [])

  function check(): boolean {
    const t = token.trim()
    const tErr = TOKEN.test(t) ? null : 'Enter a token like PERSON_c97ab2.'
    const rErr =
      reason.trim().length >= MIN_REASON ? null : 'Reason must be at least 10 characters.'
    setTokenErr(tErr)
    setReasonErr(rErr)
    if (tErr) tokenRef.current?.focus()
    else if (rErr) reasonRef.current?.focus()
    return !tErr && !rErr
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    setFormErr(null)
    if (check()) setConfirming(true)
  }

  async function confirm() {
    setBusy(true)
    try {
      const r = await reveal(token.trim(), reason.trim())
      setShown({ token: r.token, value: r.value, logged: r.logged_as })
      setReason('')
    } catch (e) {
      if (e instanceof ApiError && e.field === 'reason') setReasonErr(e.message)
      else if (e instanceof ApiError && e.code === 'unknown_token') setTokenErr('Unknown token.')
      else if (e instanceof ApiError && e.code === 'forbidden')
        setFormErr('Only admins can do this.')
      else if (e instanceof ApiError && e.code === 'vault_integrity')
        setFormErr('Vault entry failed integrity check.')
      else if (e instanceof ApiError && e.status === 429) setFormErr(e.message)
      else setFormErr('Service unavailable. Try again shortly.')
    } finally {
      setBusy(false)
      setConfirming(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-[560px]">
      <p className="body-6 text-ink-muted">
        Every request is saved in the audit log, including refused ones.
      </p>
      {shown ? (
        <ValueBox shown={shown} onHide={hideValue} />
      ) : (
        <form noValidate onSubmit={submit} className="flex flex-col gap-4">
          {formErr && <Banner tone="error">{formErr}</Banner>}
          <Field
            ref={tokenRef}
            label="Token"
            name="token"
            autoComplete="off"
            spellCheck={false}
            className="font-mono"
            value={token}
            error={tokenErr}
            onChange={(e) => setToken(e.target.value)}
          />
          <TextArea
            ref={reasonRef}
            label="Reason"
            rows={3}
            maxLength={500}
            help="Saved in the audit log."
            value={reason}
            error={reasonErr}
            onChange={(e) => setReason(e.target.value)}
          />
          <div>
            <Button type="submit">Show value</Button>
          </div>
        </form>
      )}
      <Dialog
        open={confirming}
        title={`Show the real value of ${token.trim()}?`}
        confirmLabel="Show value"
        confirmBusyLabel="Showing value"
        busy={busy}
        onConfirm={() => void confirm()}
        onClose={() => setConfirming(false)}
      >
        Your name and reason are saved in the audit log.
      </Dialog>
    </div>
  )
}

function ValueBox({ shown, onHide }: { shown: Shown; onHide: () => void }) {
  const [paused, setPaused] = useState(false)
  const [left, setLeft] = useState(HIDE_AFTER_S)
  const box = useRef<HTMLElement>(null)
  const remainingMs = useRef(HIDE_AFTER_S * 1000)

  // Focus the box (not a control) so keyboard users keep their place without pausing the
  // timer; hovering it or tabbing to Hide pauses it (DESIGN 11).
  useEffect(() => box.current?.focus(), [])

  // One hide timer for the time left; pausing stores what is left and stops it.
  useEffect(() => {
    if (paused) return
    const started = Date.now()
    const hideTimer = setTimeout(onHide, remainingMs.current)
    const tick = setInterval(() => {
      const ms = remainingMs.current - (Date.now() - started)
      setLeft(Math.max(0, Math.ceil(ms / 1000)))
    }, 250)
    return () => {
      clearTimeout(hideTimer)
      clearInterval(tick)
      remainingMs.current = Math.max(0, remainingMs.current - (Date.now() - started))
    }
  }, [paused, onHide])

  return (
    <section
      ref={box}
      tabIndex={-1}
      aria-label="Real value"
      className="rounded-lg border border-sign bg-paper p-6 flex flex-col gap-3 focus:outline-none"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <p role="status" className="body-6 text-risk-low">
        Value shown and logged{shown.logged !== null ? ` as record ${shown.logged}` : ''}.
      </p>
      <p className="caption-2 text-ink-muted font-mono">{shown.token}</p>
      <p className="heading-6 text-ink break-all select-all">{shown.value}</p>
      <div className="flex items-center gap-4">
        <Button
          variant="text"
          onClick={onHide}
          onFocus={() => setPaused(true)}
          onBlur={() => setPaused(false)}
        >
          Hide
        </Button>
        <span className="caption-2 text-ink-muted tabular-nums">
          {paused ? 'Hiding paused' : `Hides in ${left} s`}
        </span>
      </div>
    </section>
  )
}
