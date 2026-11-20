import { useEffect } from 'react'
import { ResetLearning } from '../features/admin/ResetLearning'
import { RevealForm } from '../features/admin/RevealForm'
import { RulesForm } from '../features/admin/RulesForm'

// S5 (DESIGN 12): two sections, each with its own title and save action.
export function AdminRules() {
  useEffect(() => {
    document.title = 'Rules and vault · Privacy Guardian'
  }, [])
  return (
    <div className="flex flex-col gap-12 max-w-[760px]">
      <h1 className="heading-5">Rules and vault</h1>
      <section aria-labelledby="rules-title" className="flex flex-col gap-4">
        <h2 id="rules-title" className="heading-6">
          Fixed rules
        </h2>
        <RulesForm />
      </section>
      <section
        aria-labelledby="reveal-title"
        className="flex flex-col gap-4 border-t border-rule pt-8"
      >
        <h2 id="reveal-title" className="heading-6">
          Show a real value
        </h2>
        <RevealForm />
      </section>
      <section
        aria-labelledby="learning-title"
        className="flex flex-col gap-4 border-t border-rule pt-8"
      >
        <h2 id="learning-title" className="heading-6">
          Learning
        </h2>
        <ResetLearning />
      </section>
    </div>
  )
}
