/** Plain words for the scan page (DESIGN 5.7, 5.8, 13). */

export const STEPS = [
  'Reading file',
  'Finding personal data',
  'Combining results',
  'Choosing what to hide',
  'Checking for leaks',
] as const

const CLUES: Record<string, string> = {
  gender: 'gender',
  age_year: 'exact age',
  age_range: 'age range',
  dob: 'date of birth',
  birth_year: 'birth year',
  city: 'city',
  pin: 'PIN code',
  pin_prefix: 'first digits of the PIN code',
  street_address: 'street address',
}

export function clueWords(clues: string[]): string {
  return clues.map((c) => CLUES[c] ?? c.replace(/_/g, ' ')).join(', ')
}

/** Two significant figures, rounded DOWN: fewer matching people means easier to identify,
 * so rounding down never makes a file sound safer than it is. */
function twoFigures(n: number, decimals = false): number {
  const digits = Math.floor(Math.log10(n)) - 1
  const step = 10 ** (decimals ? digits : Math.max(0, digits))
  return Math.round(Math.floor(n / step) * step * 10) / 10 // drop float noise like 3.4999
}

/** Indian number words for big counts: "70 crore", "3.5 lakh", else "1,700". */
function people(n: number): string {
  if (n >= 1e7) return `${twoFigures(n / 1e7, true).toLocaleString('en-IN')} crore`
  if (n >= 1e5) return `${twoFigures(n / 1e5, true).toLocaleString('en-IN')} lakh`
  return twoFigures(n).toLocaleString('en-IN')
}

/** "About 1,700 people match what is left in this file." (DESIGN 13: never "k"). */
export function matchSentence(est: number, clues: string[] = ['any']): string {
  if (clues.length === 0) return 'No clues left in this file point to a person.'
  if (est < 2) return 'What is left in this file may point to one person.'
  return `About ${people(est)} people match what is left in this file.`
}

const REASONS: Record<string, string> = {
  'low confidence': 'Not sure this is personal data.',
  'ambiguous name': 'This name could belong to more than one person here.',
  'unreliable type': 'Answers for this kind of data have often been corrected.',
}

export function reasonWords(reason: string): string {
  return REASONS[reason] ?? reason
}
