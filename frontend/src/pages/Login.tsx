import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { safeNext } from '../app/safeNext'
import { useLogin, useSession } from '../features/auth/session'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Field } from '../ui/Field'

// S1 (DESIGN 12, PRD 12). One shared error for wrong email or password: never a hint
// about which one was wrong.
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const WRONG = 'Wrong email or password.'

function emailError(v: string): string | null {
  if (!v.trim()) return 'Enter your email address.'
  return EMAIL.test(v.trim()) ? null : 'Enter an email address like name@example.com.'
}

function loginError(e: unknown): string {
  if (!(e instanceof ApiError)) return 'Service unavailable. Try again shortly.'
  if (e.code === 'auth_failed' || (e.status === 422 && e.field === 'password')) return WRONG
  if (e.code === 'rate_limited') return e.message // "Too many tries. Wait N seconds."
  if (e.status === 0 || e.status >= 500) return 'Service unavailable. Try again shortly.'
  return e.message
}

export function Login() {
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const ended = (useLocation().state as { ended?: boolean } | null)?.ended === true
  const session = useSession()
  const login = useLogin()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [emailErr, setEmailErr] = useState<string | null>(null)
  const [passwordErr, setPasswordErr] = useState<string | null>(null)
  const [formErr, setFormErr] = useState<string | null>(null)
  const emailRef = useRef<HTMLInputElement>(null)
  const passwordRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    document.title = 'Log in · Privacy Guardian'
  }, [])

  if (session.data?.user) return <Navigate to={next} replace />

  function submit(e: FormEvent) {
    e.preventDefault()
    setFormErr(null)
    const eErr = emailError(email)
    const pErr = password ? null : 'Enter your password.'
    setEmailErr(eErr)
    setPasswordErr(pErr)
    if (eErr) return emailRef.current?.focus()
    if (pErr) return passwordRef.current?.focus()
    login.mutate(
      { email: email.trim(), password },
      {
        onError: (err) => {
          setFormErr(loginError(err))
          setPassword('')
          passwordRef.current?.focus()
        },
      },
    )
  }

  return (
    <div className="min-h-dvh bg-desk flex flex-col items-center px-4 pt-24 pb-8">
      <main id="main" className="w-full max-w-[360px] flex flex-col gap-8">
        <header className="flex flex-col gap-2">
          <h1 className="heading-5 text-ink text-balance">Privacy Guardian</h1>
          <p className="body-3 text-ink-muted text-balance">
            Find and hide personal data before you share a file.
          </p>
        </header>
        <form
          noValidate
          onSubmit={submit}
          aria-labelledby="login-title"
          className="rounded-lg border border-rule bg-paper p-6 flex flex-col gap-4"
        >
          <h2 id="login-title" className="heading-6">
            Log in
          </h2>
          {ended && !formErr && <Banner tone="info">Please log in again.</Banner>}
          {formErr && <Banner tone="error">{formErr}</Banner>}
          <Field
            ref={emailRef}
            label="Email"
            type="email"
            name="email"
            autoComplete="username"
            inputMode="email"
            maxLength={254}
            value={email}
            error={emailErr}
            onChange={(e) => setEmail(e.target.value)}
            onBlur={() => email && setEmailErr(emailError(email))}
          />
          <Field
            ref={passwordRef}
            label="Password"
            type="password"
            name="password"
            autoComplete="current-password"
            maxLength={128}
            value={password}
            error={passwordErr}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Button type="submit" loading={login.isPending} loadingLabel="Logging in">
            Log in
          </Button>
        </form>
        <p className="caption-2 text-ink-muted">No account yet? Ask your admin to create one.</p>
      </main>
      <footer className="mt-auto pt-8">
        <Link
          to="/privacy"
          className="caption-2 text-sign hover:underline inline-block pointer-coarse:py-3"
        >
          Privacy and terms
        </Link>
      </footer>
    </div>
  )
}
