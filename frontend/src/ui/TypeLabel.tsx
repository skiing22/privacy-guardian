// DESIGN 5.4: 8 px family square + type name. The words carry the meaning, the square
// only helps find matching marks on the sheet.
export type Family = 'identity' | 'contact' | 'id' | 'other'

const SQUARE: Record<Family, string> = {
  identity: 'bg-hl-identity',
  contact: 'bg-hl-contact',
  id: 'bg-hl-id',
  other: 'bg-hl-other',
}

const NAMES: Record<string, string> = {
  PERSON: 'Name',
  AGE: 'Age',
  GENDER: 'Gender',
  PHONE: 'Phone',
  EMAIL: 'Email',
  ADDRESS: 'Address',
  LOCATION: 'Place',
  IP_ADDRESS: 'IP address',
  AADHAAR: 'Aadhaar',
  PAN: 'PAN',
  CARD: 'Card number',
  IFSC: 'IFSC',
  GOV_ID: 'Government ID',
  DATE: 'Date',
  ORG: 'Organisation',
}

export function typeName(piiType: string): string {
  return NAMES[piiType] ?? piiType
}

export function TypeLabel({ piiType, family }: { piiType: string; family: Family }) {
  return (
    <span className="inline-flex items-center gap-2 caption-4 text-ink">
      <span
        aria-hidden
        className={`h-2 w-2 rounded-sm border border-rule-strong ${SQUARE[family]}`}
      />
      {typeName(piiType)}
    </span>
  )
}
