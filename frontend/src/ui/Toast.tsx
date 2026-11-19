import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'

// DESIGN 5.9: bottom left, 4 s, confirmations only. Errors that need action are banners.
type Toast = { id: number; text: string }
const Ctx = createContext<(text: string) => void>(() => undefined)

export function useToast(): (text: string) => void {
  return useContext(Ctx)
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const next = useRef(0)
  const show = useCallback((text: string) => {
    next.current += 1
    const id = next.current
    setToasts((t) => [...t, { id, text }])
  }, [])
  return (
    <Ctx.Provider value={show}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="fixed bottom-4 left-4 right-4 sm:right-auto z-50 flex flex-col gap-2"
      >
        {toasts.map((t) => (
          <ToastItem
            key={t.id}
            text={t.text}
            onDone={() => setToasts((all) => all.filter((x) => x.id !== t.id))}
          />
        ))}
      </div>
    </Ctx.Provider>
  )
}

function ToastItem({ text, onDone }: { text: string; onDone: () => void }) {
  const [paused, setPaused] = useState(false)
  useEffect(() => {
    if (paused) return
    const t = setTimeout(onDone, 4000)
    return () => clearTimeout(t)
  }, [paused, onDone])
  return (
    <div
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      className="rounded-md bg-ink text-white body-6 px-3 py-2 max-w-[360px] shadow-dialog"
    >
      {text}
    </div>
  )
}
