import { FileText, WarningCircle } from '@phosphor-icons/react'
import { useId, useRef, useState, type DragEvent } from 'react'
import { formatBytes } from '../lib/format'
import { Button } from './Button'

// DESIGN 5.9: dashed rule-strong border on paper; drag over: sign border, sign-soft fill.
// The whole area is a real button for keyboard users; dropping is an extra, not the only way.
type Props = {
  file: File | null
  accept: string
  hint: string
  error?: string | null
  disabled?: boolean
  onFile: (f: File | null) => void
}

export function FileDrop({ file, accept, hint, error, disabled, onFile }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const id = useId()
  const errorId = error ? `${id}-error` : undefined

  function drop(e: DragEvent) {
    e.preventDefault()
    setOver(false)
    if (disabled) return
    const f = e.dataTransfer.files[0]
    if (f) onFile(f)
  }

  return (
    <div className="flex flex-col gap-2">
      <input
        ref={input}
        id={id}
        type="file"
        accept={accept}
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          onFile(e.target.files?.[0] ?? null)
          e.target.value = '' // choosing the same file again still fires
        }}
      />
      {file ? (
        <div
          className={`flex items-center gap-3 rounded-md border bg-paper px-3 py-3 ${error ? 'border-risk-high' : 'border-rule-strong'}`}
        >
          <FileText size={20} aria-hidden className="shrink-0 text-ink-muted" />
          <div className="min-w-0 flex-1">
            <p className="body-6 text-ink truncate">{file.name}</p>
            <p className="caption-2 text-ink-muted">{formatBytes(file.size)}</p>
          </div>
          <Button variant="text" onClick={() => onFile(null)} disabled={disabled}>
            Remove file
          </Button>
        </div>
      ) : (
        <button
          type="button"
          disabled={disabled}
          aria-describedby={errorId}
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setOver(true)
          }}
          onDragLeave={() => setOver(false)}
          onDrop={drop}
          className={[
            'w-full rounded-md border-2 border-dashed px-4 py-10 body-3 text-ink-muted text-balance',
            'transition-colors duration-200 ease-base disabled:opacity-40',
            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sign',
            over ? 'border-sign bg-sign-soft' : 'border-rule-strong bg-paper hover:bg-desk',
          ].join(' ')}
        >
          {hint}
        </button>
      )}
      {error && (
        <p id={errorId} className="caption-2 text-risk-high flex items-center gap-2" role="alert">
          <WarningCircle size={16} aria-hidden />
          {error}
        </p>
      )}
    </div>
  )
}
