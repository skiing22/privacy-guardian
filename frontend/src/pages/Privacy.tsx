import { useEffect } from 'react'

/**
 * S7 (D11, PRD 12, DATABASE 7 and 10). Plain statements only; each one matches how the
 * app actually works. If retention, backups or roles change, change this page with them.
 */
const STORED: { what: string; how: string; until: string }[] = [
  {
    what: 'Your original file and the cleaned file',
    how: 'Encrypted on this server',
    until: '7 days after the scan, or sooner when you delete it',
  },
  {
    what: 'What was found in your file (positions, types, tokens)',
    how: 'On this server',
    until: 'Deleted with the scan',
  },
  {
    what: 'The real values behind tokens',
    how: 'Encrypted on this server',
    until: 'Deleted when no scan uses them any more',
  },
  {
    what: 'Audit log of actions (scans finished, values shown, rule changes)',
    how: 'Tokens, events and reasons only: never real values, never file names',
    until: 'Kept, so nobody can quietly remove a record',
  },
  {
    what: 'Your account',
    how: 'Email and a one-way hashed password',
    until: 'Until an admin removes it',
  },
  {
    what: 'Backups',
    how: 'Daily copy of the database and files',
    until: '7 days, so a deleted document is gone from every copy within 14 days',
  },
]

export function Privacy() {
  useEffect(() => {
    document.title = 'Privacy and terms · Privacy Guardian'
  }, [])
  return (
    <article aria-labelledby="page-title" className="flex flex-col gap-10 max-w-[72ch]">
      <header className="flex flex-col gap-2">
        <h1 id="page-title" className="heading-5">
          Privacy and terms
        </h1>
        <p className="body-3 text-ink-muted">
          This tool finds personal data in files you upload and hides it before you share them. Here
          is what it keeps, for how long, and who can see it.
        </p>
      </header>

      <section aria-labelledby="where" className="flex flex-col gap-3">
        <h2 id="where" className="heading-6">
          Where your file goes
        </h2>
        <p className="body-3">
          Only to this server. The model that finds names runs here, so your text is never sent to
          another company. There are no analytics, no trackers and no outside fonts or scripts.
        </p>
      </section>

      <section aria-labelledby="stored" className="flex flex-col gap-3">
        <h2 id="stored" className="heading-6">
          What is stored, and for how long
        </h2>
        <dl className="flex flex-col border-t border-rule">
          {STORED.map((s) => (
            <div
              key={s.what}
              className="grid grid-cols-1 sm:grid-cols-[1fr_1fr] gap-x-6 gap-y-1 border-b border-rule py-3"
            >
              <dt className="title-3 text-ink">{s.what}</dt>
              <dd className="body-6 text-ink-muted flex flex-col gap-1">
                <span>{s.how}.</span>
                <span>{s.until}.</span>
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="who" className="flex flex-col gap-3">
        <h2 id="who" className="heading-6">
          Who can see it
        </h2>
        <ul className="body-3 flex flex-col gap-2 list-disc pl-5">
          <li>You see your own scans. Nobody else can open them, admins included.</li>
          <li>
            An admin can show the real value behind one token at a time, and must give a reason.
            Every request is saved in the audit log, including refused ones.
          </li>
          <li>The people who run this server hold the encryption keys.</li>
          <li>Server logs record requests, never the text of your documents.</li>
        </ul>
      </section>

      <section aria-labelledby="cookies" className="flex flex-col gap-3">
        <h2 id="cookies" className="heading-6">
          Cookies
        </h2>
        <p className="body-3">
          One cookie keeps you logged in. It ends after 8 hours without use, after 7 days at most,
          or when you log out. There are no other cookies.
        </p>
      </section>

      <section aria-labelledby="terms" className="flex flex-col gap-3">
        <h2 id="terms" className="heading-6">
          Terms
        </h2>
        <ul className="body-3 flex flex-col gap-2 list-disc pl-5">
          <li>
            The tool can miss personal data. Read the cleaned file and the risk note before you
            share it.
          </li>
          <li>Upload only documents you are allowed to process.</li>
          <li>Questions about your data go to the admin of this server.</li>
        </ul>
      </section>
    </article>
  )
}
