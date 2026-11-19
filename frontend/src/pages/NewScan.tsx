import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { scanKeys, startScan } from '../api/scans'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { FileDrop } from '../ui/FileDrop'
import { TextArea } from '../ui/TextArea'

// S3 (DESIGN 12, PRD 12). Checks run here first for quick answers; the server checks
// everything again (API 4.5), so these are a convenience, not a gate.
const MAX_MB = 10
const MAX_BYTES = MAX_MB * 1024 * 1024
const MAX_TEXT = 200_000
const EXTENSIONS = ['.txt', '.md', '.pdf', '.docx', '.csv']
const ACCEPT = EXTENSIONS.join(',')
const HINT = 'Drop a file here or choose one. TXT, PDF, DOCX or CSV, up to 10 MB.'

export function fileProblem(f: File): string | null {
  const name = f.name.toLowerCase()
  if (!EXTENSIONS.some((ext) => name.endsWith(ext))) return 'Only TXT, PDF, DOCX, CSV.'
  if (f.size > MAX_BYTES) return `File too large (max ${MAX_MB} MB).`
  if (f.size === 0) return 'This file is empty.'
  return null
}

export function NewScan() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [text, setText] = useState('')
  const [fileErr, setFileErr] = useState<string | null>(null)
  const [textErr, setTextErr] = useState<string | null>(null)
  const [formErr, setFormErr] = useState<string | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const textRef = useRef<HTMLTextAreaElement>(null)
  const busy = progress !== null

  useEffect(() => {
    document.title = 'New scan · Privacy Guardian'
  }, [])

  // DESIGN 7: focus the field with the error. After render, because during the upload the
  // text box was disabled and could not take focus.
  useEffect(() => {
    if (textErr && !busy) textRef.current?.focus()
  }, [textErr, busy])

  const ready = file ? !fileErr : text.trim().length > 0 && text.length <= MAX_TEXT

  function chooseFile(f: File | null) {
    setFormErr(null)
    setFile(f)
    setFileErr(f ? fileProblem(f) : null)
  }

  function showServerError(e: unknown) {
    if (!(e instanceof ApiError)) return setFormErr('Service unavailable. Try again shortly.')
    if (e.code === 'auth_required' || e.code === 'session_expired') return // guard takes over
    const fieldErr = ['file_too_large', 'unsupported_type', 'empty_input', 'file_unreadable']
    if (e.field === 'text') return setTextErr(e.message) // focus moves in the effect below
    if (file && fieldErr.includes(e.code)) return setFileErr(e.message)
    setFormErr(
      e.status === 0 || e.status >= 500 ? 'Service unavailable. Try again shortly.' : e.message,
    )
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!ready || busy) return
    setFormErr(null)
    setTextErr(null)
    setProgress(0)
    startScan(file ? { file } : { text }, setProgress)
      .then((r) => {
        void qc.invalidateQueries({ queryKey: scanKeys.all })
        navigate(`/scans/${r.id}`)
      })
      .catch((err: unknown) => {
        setProgress(null)
        showServerError(err)
      })
  }

  return (
    <section aria-labelledby="page-title" className="max-w-[680px] flex flex-col gap-8">
      <h1 id="page-title" className="heading-5">
        New scan
      </h1>
      <form noValidate onSubmit={submit} className="flex flex-col gap-6">
        {formErr && <Banner tone="error">{formErr}</Banner>}
        <FileDrop
          file={file}
          accept={ACCEPT}
          hint={HINT}
          error={fileErr}
          disabled={busy}
          onFile={chooseFile}
        />
        <TextArea
          ref={textRef}
          label="Or paste text"
          rows={10}
          value={text}
          disabled={!!file || busy}
          maxLength={MAX_TEXT}
          error={textErr}
          help={
            file
              ? 'Remove the file to paste text instead.'
              : `Up to ${MAX_TEXT.toLocaleString('en-IN')} characters.`
          }
          onChange={(e) => {
            setText(e.target.value)
            setTextErr(null)
          }}
        />
        {busy && (
          <div className="flex flex-col gap-2">
            <p className="caption-2 text-ink-muted" aria-live="polite">
              {progress < 1 ? `Uploading, ${Math.round(progress * 100)}%` : 'Starting scan'}
            </p>
            <div
              role="progressbar"
              aria-label="Upload"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progress * 100)}
              className="h-1 w-full rounded-sm bg-rule overflow-hidden"
            >
              <div
                className="h-full bg-sign origin-left transition-transform duration-200 ease-base"
                style={{ transform: `scaleX(${progress})` }}
              />
            </div>
          </div>
        )}
        <div>
          <Button type="submit" disabled={!ready} loading={busy} loadingLabel="Starting scan">
            Start scan
          </Button>
        </div>
      </form>
    </section>
  )
}
