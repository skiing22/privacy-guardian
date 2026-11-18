# DESIGN: Privacy Guardian Agent v2

> Single source of truth for visual design and UX. Product scope comes from **PRD.md**; this file never adds features (two proposed additions are flagged in section 15). Screen IDs (S1–S6) and decisions (D1–D10) refer to PRD.md.

---

## 0. Where these rules come from

This file follows four design skills, applied to what this product is: a **web app tool**, not a marketing site.

| Skill | What it decides here |
| --- | --- |
| **frontend-design** | Visual direction grounded in the subject; one memorable moment; no generic AI traits; plain, specific copy |
| **landing-page-design** (Part B, visual system) | Font list, one typeface, Tailwind type scale and named text styles, spacing tokens, radius rules, flat backgrounds, icons, motion curve, nav behaviour, interactive states, copy rules, ship requirements |
| **design-taste-frontend** (tasteskill) | Anti-slop rules: no violet, sharp radius for developer and security tools, hover and press on everything clickable, no scroll fade-ins, one system (one button pair, one radius scale, one link look) |
| **ui-ux-pro-max** | Priority order for checks: accessibility, touch, performance, style, layout, type and colour, animation, forms, navigation |

**ui-ux-pro-max note:** its search database and scripts were not available, so no palette or font was taken from its database. Only its priority table and rule categories are used (its documented fallback).

### Conflicts and how they are resolved

| Conflict | Resolution | Why |
| --- | --- | --- |
| landing-page-design Part A (landing structure, FAQ, mandatory tagline reveal) vs. PRD with no landing page | Part A applies **only** to the optional landing page S0 (section 15, D12). Not to S1–S6 | Part A is for pages that sell; S1–S6 are tools |
| landing-page-design "scroll reveal on every section" vs. tasteskill and frontend-design "never fade in on scroll" | **No scroll reveals in the app.** On S0 only, the one tagline reveal | App pages are panels, not scrolling sections; two of three skills forbid it |
| landing-page-design hero heading gradient | **Not used.** The app has no hero. S0 (if approved) uses flat `ink` | Text gradients are a generated-page tell (frontend-design) |
| landing-page-design `duration-500` for layout changes vs. fast keyboard review | 500 ms for panels and dialogs; review answers swap content with a 200 ms opacity change | landing-page-design allows ≥ 200 ms for opacity; ui-ux-pro-max asks for context-aware timing |
| landing-page-design button padding 8/12 (40 px tall) vs. ui-ux-pro-max 44 px touch target | Keep 8/12 padding; on touch screens buttons get a 44 px minimum height | Both rules satisfied |
| Earlier DESIGN.md: violet "stamp" accent, Mukta + Source Serif | **Replaced**: blue-black ink accent, Manrope + Geist Mono | tasteskill bans violet; landing-page-design allows one typeface (+ Geist Mono for data) and lists approved fonts |
| tasteskill photographs, shader effects, one section per screen | **Not used** in the app; considered only for S0 | Those rules are for company sites; a privacy tool shows the user's own document, never stock photos |

---

## 1. Visual direction

**Subject:** a tool that marks personal data in a document and hides it before the document is shared.
**Audience:** HR, research and compliance staff in India, often busy, often reviewing many files.
**Primary job:** turn an unsafe file into a safe, still useful one, and show exactly what changed.

**The document is the product.** The interface is a quiet desk. The user's file lies on it as a sheet of paper. Our work appears *on the sheet* as marks, the way a reviewer marks up a printout with highlighter pens and signs it in blue-black ink.

- **Highlighter pens:** found items are marked in soft highlighter colours, one colour per family of data.
- **Blue-black ink:** the colour of the signature on an Indian office form. It is the single accent and marks only the user's decisive actions.
- **The memorable moment:** the **redaction pass** (section 9). When a scan finishes, each highlight turns into its result, a token, a mask or an ink bar, in place on the page.

### Principles

1. **Show it on the page.** Every finding is visible in the document, in context. Lists support the page; they never replace it.
2. **Every choice explains itself.** Any item opens to show type, confidence, action and reason in plain words.
3. **Colour means something or it is not used.** Highlighter = data family. Ink blue = primary action. Red, amber, green = risk. Nothing decorative.
4. **Calm by default, loud only for risk.** The only large coloured element is a HIGH or DIRECT risk banner.
5. **Keyboard first.** Reviewing 20 items never needs the mouse.
6. **Plain words.** "Keep visible", not "allowlist". "About 1,700 people match", not "k equals 1,750".

### Self-review against generic output

| Default an AI page reaches for | This design instead |
| --- | --- |
| Identical rounded cards with soft grey shadows | Flat panels with one border; only the paper sheet and dialogs cast a shadow, because they sit above the desk |
| Bright SaaS blue (#3B82F6) or violet accent | Dark blue-black ink, used for actions only |
| Cream background with a serif display and clay accent | Cool desk grey, white paper, one sans family |
| Big number KPI row on the home page | A plain table of scans |
| All-caps eyebrow labels, `A · B · C` meta, `→` on buttons | Sentence case labels, separate columns, verb + object buttons |
| Monospace for small labels | Mono only for tokens and IDs, which are literally machine strings |
| Fade-up on every section | One redaction pass; everything else moves only when the user acts |

---

## 2. Colour

Light theme only for MVP. Screens use token names, never raw hex. Backgrounds are flat; **no gradients anywhere**.

### 2.1 Base

| Token | Hex | Use |
| --- | --- | --- |
| `desk` | `#ECEFF2` | App background |
| `paper` | `#FFFFFF` | Document sheet, panels, inputs, nav bar |
| `ink` | `#1D232B` | Main text, icons, redaction bars |
| `ink-muted` | `#58626E` | Help text, timestamps, secondary text |
| `rule` | `#D3D8DE` | Borders, dividers, table lines |
| `rule-strong` | `#98A2AD` | Input borders |
| `sign` | `#2A44B0` | Primary actions, links, focus ring, current nav item |
| `sign-soft` | `#E7EBFA` | Selected row, selected segment, drag-over |
| `sign-hover` | `#22398F` | Primary button hover |

### 2.2 Highlighters (data families)

15 PII types fold into **4 families**, so users learn 4 colours, not 15.

| Token | Hex (fill) | Family | PII types |
| --- | --- | --- | --- |
| `hl-identity` | `#FFEFA3` yellow | Who someone is | PERSON, AGE, GENDER |
| `hl-contact` | `#CBEED4` green | How to reach or find them | PHONE, EMAIL, ADDRESS, LOCATION, IP_ADDRESS |
| `hl-id` | `#FAD2DF` pink | Government and financial IDs | AADHAAR, PAN, CARD, IFSC, GOV_ID |
| `hl-other` | `#E3E6EA` grey | Dates and the rest | DATE, ORG |

- Text on a highlighter is always `ink` (contrast ≥ 12:1).
- Colour is never the only signal: every mark also has a type name (section 11).
- `hl-other` is grey, not blue, so it is never confused with the `sign` action colour.

### 2.3 Risk and status

| Token | Text / border | Background | Use |
| --- | --- | --- | --- |
| `risk-low` | `#1F6B45` | `#E3F3EA` | Low risk, success |
| `risk-medium` | `#8A5300` | `#FCEFD9` | Medium risk, warnings |
| `risk-high` | `#B3261E` | `#FBE4E2` | High risk, errors, tampered audit row |
| `risk-direct` | `#FFFFFF` | `#8C1D18` | "Personal data visible" only; the loudest thing in the app |

All pairs meet WCAG AA (≥ 4.5:1).

---

## 3. Typography

**One typeface: Manrope.** Geist Mono is used next to it only where a monospace is needed: tokens (`PERSON_c97ab2`) and raw IDs.

Why Manrope: it is on the approved list, its open, slightly geometric shapes stay clear at 12–14 px in dense tables, and its numerals are distinct, which matters in a tool full of phone and ID numbers. The user's document is set apart from our interface by the paper sheet and a larger size, not by a second family.

Rules: no italics anywhere; weights 400, 500, 600 only (no 800 or 900); sentence case; no all caps.

### 3.1 Text styles

Every text uses one named style. Sizes are Tailwind steps only.

| Style | Step | Size / line height | Weight | Used for |
| --- | --- | --- | --- | --- |
| Heading 5 | `text-2xl` | 24 / 32 | 600 | Page titles |
| Heading 6 | `text-xl` | 20 / 28 | 600 | Panel and section titles, risk sentence |
| Title 3 | `text-base` | 16 / 24 | 500 | Nav items, item names, review card question |
| Title 4 | `text-sm` | 14 / 20 | 500 | Table headers, field labels |
| Body 3 | `text-base` | 16 / 24 | 400 | Body text, inputs |
| Body 6 | `text-sm` | 14 / 20 | 400 | Table cells, item reasons |
| **Body 7** (new) | `text-lg` | 18 / 28 | 400 | Document sheet text (original and cleaned) |
| Button-md | `text-base` | 16 / 24 | 600 | Main buttons |
| Button-sm | `text-sm` | 14 / 20 | 600 | Table and nav buttons |
| Caption 2 | `text-sm` | 14 / 20 | 400 | Help text under fields |
| Caption 4 | `text-xs` | 12 / 16 | 500 | Type labels on marks, timestamps, badges |
| Token | Geist Mono, same step as surrounding text | | 500 | Tokens and IDs |

Headings 1–4 are not used in the app (no hero). They are reserved for S0.

### 3.2 Copy rules

- **No hyphens in sentences.** Rewrite instead ("follow up", not "follow-up"). Data values keep their real form (`30-34`, `1800-425-3800`, `KL11 20190012345`).
- **No orphans.** Headings balance their lines; paragraphs avoid a single last word.
- Line length: document sheet max **72 characters**; interface paragraphs max **65 characters**.
- Tables use tabular numerals.
- Banned words: revolutionize, supercharge, cutting edge, effortless, seamless, world class, harness, unlock.
- No exclamation marks. Confirmations are specific ("Answers saved for 5 items"). Errors say what failed and what to do.

---

## 4. Spacing, shape and layout

### 4.1 Spacing

Only: `0, 2, 4, 8, 12, 16, 24, 32, 40, 48, 64, 80, 96` px.

| Where | Value |
| --- | --- |
| Inside a button | 8 vertical, 12 horizontal |
| Inside inputs | 8 vertical, 12 horizontal |
| Label to field, row to row | 8 |
| Items in a panel | 12 |
| Groups in a panel, panel padding | 24 |
| Page regions | 32 |
| Page top padding | 48 |

### 4.2 Radius

Sharp scale (tasteskill: developer and security tools). Tailwind values only.

| Element | Radius |
| --- | --- |
| Marks, tokens, type labels | `rounded-sm` 2 px (a marker stroke, not a pill) |
| Buttons, inputs, badges, segmented control | `rounded-md` 6 px |
| Panels, dialogs, nav bar | `rounded-lg` 8 px |
| Document sheet | `rounded-sm` 2 px (paper has square corners) |

Nested rule: inner radius = outer radius minus the gap, only when the result is above 2 px; otherwise the inner shape is square. Example: a button inside a panel with 24 px padding keeps its own 6 px.

### 4.3 Borders and depth

- Borders go all the way round or not at all; never a one-sided card border. (A table row's 1 px bottom line is a table rule, not a card border.)
- Exception for status: the tampered audit row and selected item row get a full 2 px outline, not a left stripe.
- Shadow only on the **document sheet** (paper on a desk) and **dialogs** (above everything). Everything else is flat with a `rule` border.

### 4.4 Grid and widths

- App content max width **1280 px**, side gutters 24 px (16 px on phones).
- Document sheet: fits 72 characters of Body 7 (about 680 px) plus 48 px padding.
- Side panel: **360 px** on desktop.
- All content **left aligned**. Only empty states are centred.

### 4.5 App shell

```
                 ┌───────────────────────────────────────────────┐
                 │ Privacy Guardian   Scans  Rules & vault*  Audit log*  [SR] │  ← floating bar, 16 px from top
                 └───────────────────────────────────────────────┘
   Page title                                          [Primary action]

   page content (sheet + panel, or table)
```
`*` admin only. `[SR]` user menu (initials).

---

## 5. Reusable components

One system: one button pair, one panel style, one radius scale, one link look.

### 5.1 Buttons

| Variant | Look | Use |
| --- | --- | --- |
| Primary | `sign` fill, white text, Button-md | The one main action in a view: Start scan, Submit answers, Show value, Verify log, Save rules |
| Secondary | `paper` fill, `rule-strong` border, `ink` text | Other actions: Download report, Cancel |
| Text | No border, `sign` text, underline draws in on hover | Small actions in panels and tables: Open, Retry, Undo |
| Danger | `paper` fill, `risk-high` border and text | Delete scan, Reset learning |

- Label = verb + object. No arrows, no emoji.
- At most one primary button per view.
- **States:** hover = background one shade darker; press = `translateY(1px)`; focus = 2 px `sign` ring, 2 px offset; disabled = 40% opacity, no hover; loading = label changes to the action in progress ("Starting scan") and the button is disabled. No spinners.
- Height 40 px on mouse screens, at least 44 px on touch screens.

### 5.2 Mark (found item on the sheet)

- Fill = family colour; 2 px radius; 2 px horizontal padding so neighbouring marks never touch.
- Hover or focus: a type label (Caption 4) sits above the mark: "Phone, 97% sure".
- Click or Enter: selects the item and opens it in the side panel.
- States: default; focused (2 px `sign` outline); needs review (2 px `sign` underline); selected (`sign` outline, matching panel row selected).

### 5.3 Result (on the cleaned sheet)

| Action (user wording) | Shown as |
| --- | --- |
| Replace with token | Geist Mono token on the family colour: `PERSON_c97ab2` |
| Mask | Masked text in the sheet font with a family-colour underline: 98\*\*\* \*\*\*45 |
| Generalize | New value with a dotted family-colour underline: 30-34 |
| Remove | Solid `ink` bar the width of the original; "Removed" on hover |
| Keep | Original text, plain |

Hovering a token outlines every occurrence of the same token.

### 5.4 Labels and badges

- **Type label:** 8 px family-colour square + type name, Caption 4. Used in tables and the panel.
- **Risk badge:** risk colour pair: "Low risk", "Medium risk", "High risk", "Personal data visible".
- **Status badge:** `rule` border, `ink-muted` text: "Running", "Done", "Failed". "Needs review" uses `sign` text.

### 5.5 Item row

```
[■] Phone     +91 98470 12345     Replace with token
    Found by rules and the model, 99% sure. Phones are sensitive by default.
```
Facts on line 1 (Title 3 + Body 6), reason on line 2 (Body 6, `ink-muted`). Selecting a row scrolls the sheet to the mark.

### 5.6 Review card

```
┌ Needs your answer: 2 of 5 ─────────────────────────────────┐
│ …send the documents to 22, Nehru Nagar, Bhopal 462003…     │  ← Body 7 on paper, item marked
│                                                            │
│ Is this personal data? Address, 58% sure.                  │  ← Title 3
│                                                            │
│ [1  Protect]   [2  Keep visible]   [3  Not personal data]  │  ← secondary buttons, key hint inside
└────────────────────────────────────────────────────────────┘
```
- Always three answers, this order, these words.
- An answer moves to the next item; "Undo" (text button) shows for 5 seconds.
- "Submit answers" (primary) appears only when every item is answered.
- "2 of 5" is a real sequence, so a number is right here.

### 5.7 Progress steps

A real sequence, so numbered.
```
✓ 1  Reading file
✓ 2  Finding personal data
● 3  Combining results
  4  Choosing what to hide
  5  Checking for leaks
```
Current step: `sign` dot, Title 3. A verifier loop reads "Checking for leaks, round 2 of 3". On failure the step turns `risk-high` with the error under it.

### 5.8 Risk banner

- Sentence first: **"About 1,700 people match what is left in this file."** then the risk badge.
- Clues in plain words: "Visible clues: gender, age range, city."
- High: `risk-high` pair + "Do not share yet. Protect more items in the list below."
- Direct: `risk-direct` + "Personal data is still visible because of a fixed rule." + text link to that rule.

### 5.9 Other components

| Component | Rules |
| --- | --- |
| Segmented control | 2–3 options (Original, Cleaned, Compare). Selected: `sign-soft` fill, `sign` text |
| File drop | Dashed `rule-strong` border on `paper`. "Drop a file here or choose one. TXT, PDF, DOCX or CSV, up to 10 MB." Drag over: `sign` border, `sign-soft` fill |
| Table | No zebra stripes; 1 px `rule` row lines; Body 6; 44 px rows; Title 4 headers in `ink-muted`. Linked row hover: `desk` fill |
| Banner | Icon + one sentence + optional text button. Uses the risk pairs |
| Toast | Bottom left, 4 s, confirmations only. Never an error that needs action |
| Dialog | Only for actions with consequences (Show value, Reset learning). Title asks the question; primary button repeats the action |
| Skeleton | `rule` coloured blocks shaped like the real content. No shimmer, no spinners |
| Empty state | Centred in its region: one sentence saying what goes here + one action. No illustration |
| Icons | **Phosphor**, regular weight, 20 px, SVG. Never emoji. Icon-only buttons have a visible tooltip and an accessible name |

---

## 6. Navigation

- **Bar:** a compact bar that floats 16 px below the top edge, centred and sized to its content, `paper` at 85% opacity with background blur, `rule` border, 8 px radius.
- **Links:** Scans, Rules & vault (admin), Audit log (admin). Current page: `sign` text + 2 px `sign` bar under the link. No dead links.
- **New scan** is a primary button on S2, not a nav link.
- **User menu** (initials): name, role, Log out.
- **Breadcrumb** only on S4: "Scans / resume_rahul.pdf".
- **Phones:** the bar shows the name and a menu button. The icon morphs between menu and close (500 ms, base curve). The menu opens as a full height panel, `paper` at 95% with strong blur; links enter one after another, 24 px upward with fade, 60 ms apart, whole sequence capped at 400 ms.
- **URLs:** `/scans`, `/scans/new`, `/scans/{id}`, `/admin/rules`, `/admin/audit`. Back always works; a paused scan stays paused when you leave.
- A **skip to content** link is the first thing Tab reaches.

---

## 7. Forms

| Rule | Detail |
| --- | --- |
| Labels | Visible, above the field, Title 4. Never placeholder as label |
| Help text | Under the field, Caption 2, `ink-muted` |
| Required | Everything is required unless marked "(optional)" |
| Validation | On blur and on submit, in the browser and on the server. Error text in `risk-high` under its own field with an icon; field border `risk-high`; focus moves to the first error on submit |
| Error wording | What is wrong and how to fix it: "Reason must be at least 10 characters." Never "Invalid input" |
| Submit | Enabled unless a request is in flight. PRD exception: Start scan stays disabled until a file or text is given |
| Success | Same verb as the button: "Show value" → "Value shown and logged" |

Forms in the app:
- **Login (S1):** Email (format checked), Password, "Log in". One shared error for a wrong email or password.
- **Show a real value (S5):** Token (Geist Mono input), Reason (textarea, min 10 characters, help: "Saved in the audit log."), "Show value" → confirm dialog → value in a box with a "Hide" text button; it hides itself after 60 s.
- **Fixed rules (S5):** one select per PII type: Automatic (default), Keep, Generalize, Mask, Replace with token, Remove. Only valid actions are offered. "Save rules".

---

## 8. States

Wording and triggers are fixed in **PRD section 12**. Every interactive element has hover, press, focus, loading, empty and error states.

| State | Pattern |
| --- | --- |
| Page loading | Skeleton of the real layout, shown only after 300 ms |
| Action in progress | Button loading state (5.1); the page stays usable |
| Scan running | Progress steps (5.7), polled every second (D6). First scan after start: step 1 reads "Preparing the model, about 30 seconds, only the first time" |
| Empty | Empty state (5.9) in the empty region only |
| Field error | Under its own field (section 7) |
| Region error | Error banner at the top of that region with "Retry"; the rest works |
| Session ended | Back to S1 with "Please log in again"; return to the same page after login |
| Server down | Error banner under the nav; last loaded content stays visible, read only |
| 404 | Plain page: "This page does not exist." + "Go to your scans" (see D11) |

---

## 9. Motion

**Curve:** `cubic-bezier(0.22, 1, 0.36, 1)` everywhere. Never `ease`, `linear` or `ease-in-out`.
**Durations:** 500 ms for position and layout changes; 200–300 ms for colour and opacity.
**Properties:** animate only `transform` and `opacity`.

| What | Motion |
| --- | --- |
| **Redaction pass** (the one signature moment) | When a scan finishes while the user is on S4: visible marks change into their results top to bottom, each 500 ms (opacity cross-fade + 2 px settle), 30 ms apart, total capped at 1.5 s. Plays once per scan; skipped if the scan finished while the user was away |
| Button hover | Background shade, 200 ms |
| Button press | `translateY(1px)` |
| Text link | Underline draws left to right, 300 ms |
| Linked table row | Background to `desk`, 200 ms (rows never lift) |
| Panel or dialog open | Fade + 8 px rise, 500 ms |
| Review answer | Card content cross-fades, 200 ms, so fast keyboard review never waits |
| Select item | Sheet scrolls smoothly to the mark |
| Token hover | All occurrences outlined at once |
| Verify log | Result banner fades in; on tamper, the bad row scrolls into view and gets a `risk-high` outline |

**Never:** fade-in on scroll, parallax, tilt, carousels, auto-advancing tabs, looping animation.
**Reduced motion:** every movement becomes a plain opacity change; the redaction pass becomes an instant swap.

### Keyboard (S4)

| Key | Action |
| --- | --- |
| `↑` `↓` | Previous / next item |
| `1` `2` `3` | Protect / Keep visible / Not personal data |
| `Enter` | Open selected item |
| `O` `C` `B` | Original / Cleaned / Compare |
| `Z` | Undo the last answer (within 5 s) |

A "Keyboard shortcuts" text button on S4 lists these. Keys never fire while typing.

---

## 10. Responsive behaviour

Mobile first. Breakpoints: 640 px and 1024 px only.

| Width | Layout |
| --- | --- |
| < 640 px | One column. Review shows one card at a time with full width answer buttons. Tables become stacked rows (label: value). Compare view hidden |
| 640–1023 px | Sheet full width; panel becomes three tabs above the sheet: Items, Review, Risk. Compare hidden |
| ≥ 1024 px | Sheet + 360 px panel side by side. Compare: two sheets side by side, panel becomes a drawer |

Rules: no sideways scrolling at 320 px; sheet text never below 16 px; every control ≥ 44 × 44 px on touch with ≥ 8 px between targets; viewport zoom never disabled; the primary action visible on the first screen at 390 px.

---

## 11. Accessibility (WCAG 2.2 AA, checked first)

- **Contrast:** text ≥ 4.5:1; large text, icons and borders of controls ≥ 3:1.
- **Not colour alone:** each mark has a name, e.g. "Phone number, replaced with token PHONE_244a6e". Risk always has words.
- **Keyboard:** all features work by keyboard in visual order; visible 2 px focus ring on everything; dialogs trap focus and return it to the trigger.
- **Focus never hidden** under the floating nav: scrolling to a focused item keeps it below the bar.
- **Screen readers:** progress in a polite live region ("Step 3 of 5, combining results"); review card announces "Item 2 of 5, address, 58% sure"; form errors and verify results in an assertive live region.
- **Marks:** focusable in reading order; Tab moves through marks; Esc leaves the sheet.
- **Zoom** to 200% without losing content; no text in images.
- **Time:** the 5 s undo and 60 s auto-hide pause while hovered or focused.
- **Semantic HTML:** `nav`, `main`, `section`, `table`, real `button` and `a` elements; headings one level at a time.

---

## 12. Page layouts

### S1 Login
Centred 360 px column on `desk`. "Privacy Guardian" (Heading 5), one line: "Find and hide personal data before you share a file." Form on a `paper` panel. Footer links (D11).

### S2 Scans
```
Scans                                                     [New scan]
┌───────────────────────────────────────────────────────────────────┐
│ File               Started          Status         Risk           │
│ employees.csv      Today, 23:40     Needs review   —              │
│ patient_note.txt   Today, 23:52     Done           Low risk       │
└───────────────────────────────────────────────────────────────────┘
```
"Needs review" first, then newest first. Row opens S4. Empty: "No scans yet. Start your first scan." + New scan.

### S3 New scan
One column, max 680 px. File drop, then "Or paste text" (textarea, Body 7, 10 rows). "Start scan" opens S4 at once.

### S4 Scan (D7: run, review and result on one page)

```
Scans / patient_note.txt                    [Download cleaned file]  [Download report]
┌ About 1,700 people match what is left in this file.  Low risk ─────────────────────┐
│ Visible clues: gender, age range, birth year.                                      │
└────────────────────────────────────────────────────────────────────────────────────┘
[ Original | Cleaned | Compare ]
┌──────────── sheet ─────────────────────┐   ┌──── panel 360 ───────────────┐
│ Discharge summary  LOCATION_553c17     │   │ 17 items                     │
│ Hospital, LOCATION_49483f              │   │ [■] Person  Arjun Nair   ... │
│ Patient: PERSON_c97ab2, Male, age      │   │ [■] Phone   +91 98470 ...    │
│ 30-34. DOB 1992.                       │   │ ...                          │
└────────────────────────────────────────┘   │ Checked for leaks in 1 round │
                                              └──────────────────────────────┘
```
- **Running:** panel shows progress; sheet shows the original, marks appear as detection finishes.
- **Paused:** panel shows the review card; the current item is scrolled into view on the sheet.
- **Done:** risk banner, view switch, item list, downloads; the redaction pass plays once.
- **Failed:** error banner with Retry; progress shows the step that failed.
- **PDF input (D4):** "Download cleaned text (.txt)" with help "PDFs are returned as text."

### S5 Rules & vault (admin)
Two sections on one page, each with its title and own save action:
1. **Fixed rules:** PII types grouped by family, one select each, "Save rules".
2. **Show a real value:** the form in section 7, with the note "Every request is saved in the audit log, including refused ones."

### S6 Audit log (admin)
```
Audit log                                                         [Verify log]
┌ All 214 records check out and match the anchor saved on 18 Nov, 23:55. ┐
└───────────────────────────────────────────────────────────────────────┘
#     Time            Who        Event                  Details
214   18 Nov 23:55    admin1     Real value shown       PERSON_c97ab2, reason: court order 2026/77
213   18 Nov 23:52    rahul      Scan completed         scan 3f2a9c1e, low risk
```
Events in plain words ("Real value request refused", not `reidentify_denied`). Tokens in Geist Mono; never raw values and never filenames (the log is permanent; DATABASE 7.2). On tamper: "Record 0 was changed after it was saved." and the row is outlined in `risk-high` and scrolled into view.

---

## 13. Words in the interface

One name per idea, everywhere: buttons, toasts, help, audit log.

| Idea | Always say | Never say |
| --- | --- | --- |
| PII | personal data | PII, entity, span |
| Found item | item | span, detection, hit |
| Pseudonymize | replace with a token | pseudonymize |
| Redact | remove | redact, scrub |
| Review answers | Protect / Keep visible / Not personal data | approve, allowlist, false positive |
| Re-identify | show the real value | de-tokenize, reverse |
| Audit verify | verify the log | validate chain |
| Risk | "About N people match what is left" | k-anonymity, crowd size |

---

## 14. Ship checklist

- [ ] Every colour, size, space and radius comes from a token in this file
- [ ] Manrope only (+ Geist Mono for tokens and IDs); no italics; no weight above 600
- [ ] No gradients, no one-sided card borders, no violet
- [ ] One primary button per view; every button a verb + object
- [ ] Hover, press, focus, loading, empty and error states on every interactive element
- [ ] No spinners: skeletons and step lists only
- [ ] Only `transform` and `opacity` animate, on the base curve; reduced motion respected
- [ ] No hyphens in sentences, no orphans, no banned words, no exclamation marks
- [ ] Phosphor icons only, every icon-only button named
- [ ] Works at 320, 390, 768, 1024 and 1440 px with no sideways scroll
- [ ] Skip link, visible focus, semantic HTML, contrast checked
- [ ] Title, meta description, favicon on every page
- [ ] Footer links and 404 page (D11)

---

## 15. Proposed additions (need approval)

These come from the skills' ship rules but are **not** in PRD.md, so they are flagged rather than assumed.

| ID | Proposal | Source | Recommendation |
| --- | --- | --- | --- |
| **D11** | A plain **Privacy and terms** page linked from a footer on every screen, and a **404 page** | landing-page-design B10 | **Approve.** A privacy tool without a privacy notice looks careless; both are static pages, under an hour of work |
| **D12** | A one-page **public landing page (S0)** at `/` with "Try the demo" as the one action, for recruiters and reviewers | landing-page-design Part A, tasteskill | **Approve, build last (M7).** It is the first thing a recruiter sees. Rules below |

### S0 rules (only if D12 is approved)

- Layout type A (hero + sections): the product is understood from one screenshot of S4.
- **Hero:** heading names the category and buyer, e.g. "Hide personal data in Indian documents before you share them." (Heading 2, flat `ink`, max 680 px, broken where the thought breaks). Subheading with one hard fact. One action: "Try the demo". The hero visual is the **real S4 screen** with a real cleaned sample, never a stock photo or illustration.
- **Sections**, one idea per screen, in this order: what it finds (the 4 families on a real sheet); how it decides (the risk sentence); proof it was not edited (the audit verify result); how it works in three steps (a real sequence); FAQ (6 questions); final "Try the demo".
- **Tagline reveal** (mandatory in landing-page-design, the page's one scroll moment): "Removing names is not enough. What is left can still point to one person." Words turn from 30% to full `ink` one by one as they cross the middle of the screen. Reduced motion: full colour at once.
- No invented numbers, logos or testimonials. Every figure on S0 comes from `docs/results/` (and the accuracy figure waits for test set v2, D9).
- Footer: Privacy and terms, GitHub repository, decision log.
