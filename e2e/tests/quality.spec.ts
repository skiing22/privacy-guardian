import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { login, REVIEW_TEXT, startScan, SURE_TEXT, waitForResult } from './helpers'

/**
 * DESIGN 11 (WCAG 2.2 AA) and P18.2/P18.3: axe on every screen, focus never under the
 * floating nav, no sideways scrolling, touch targets of at least 44 px on phones.
 */
test.describe.configure({ mode: 'serial' })

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
let resultUrl = ''
let reviewUrl = ''

async function axe(page: Page, name: string) {
  const r = await new AxeBuilder({ page }).withTags(TAGS).analyze()
  const found = r.violations.map(
    (v) => `${v.id} (${v.nodes.length}): ${v.nodes[0]?.target.join(' ')}`,
  )
  expect(found, `axe violations on ${name}`).toEqual([])
}

test('setup: one finished scan and one paused scan', async ({ page }) => {
  await login(page)
  resultUrl = await startScan(page, SURE_TEXT)
  await waitForResult(page)
  reviewUrl = await startScan(page, REVIEW_TEXT)
  await expect(page.getByRole('heading', { name: /Needs your answer/ })).toBeVisible({
    timeout: 30_000,
  })
})

test('no axe violations on any screen', async ({ page }) => {
  await page.goto('/login')
  await axe(page, 'login')
  await page.goto('/privacy')
  await axe(page, 'privacy (logged out)')
  await login(page)
  const pages: [string, string, string][] = [
    ['scans', '/scans', 'Scans'],
    ['new scan', '/scans/new', 'New scan'],
    ['admin rules', '/admin/rules', 'Rules and vault'],
    ['audit log', '/admin/audit', 'Audit log'],
    ['privacy', '/privacy', 'Privacy and terms'],
    ['404', '/no-such-page', 'This page does not exist.'],
  ]
  for (const [name, path, heading] of pages) {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()
    await page.waitForLoadState('networkidle')
    await axe(page, name)
  }
  await page.goto(reviewUrl)
  await expect(page.getByRole('heading', { name: /Needs your answer/ })).toBeVisible()
  await axe(page, 'review')
  for (const view of ['c', 'o']) {
    await page.goto(resultUrl)
    await waitForResult(page)
    await page.keyboard.press(view)
    await axe(page, `result (${view === 'c' ? 'cleaned' : 'original'})`)
  }
})

test('focus is never hidden under the floating nav', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 600 })
  await login(page)
  await page.goto(resultUrl)
  await waitForResult(page)
  for (let i = 0; i < 25; i++) {
    await page.keyboard.press('Tab')
    // WCAG 2.4.11: nothing (the floating nav above all) covers the focused element.
    const [covered, tag] = await page.evaluate(() => {
      const el = document.activeElement
      if (!el || el === document.body) return [false, 'BODY']
      const r = el.getBoundingClientRect()
      const top = document.elementFromPoint(r.left + r.width / 2, r.top + Math.min(r.height / 2, 8))
      return [!!top && !el.contains(top) && !top.contains(el), el.tagName]
    })
    if (tag === 'BODY') continue
    expect(covered, `focused element ${i} (${tag}) is covered`).toBe(false)
  }
})

const WIDTHS = [320, 390, 768, 1024, 1440]

for (const width of WIDTHS) {
  test(`layout at ${width} px`, async ({ browser }) => {
    const touch = width < 768
    const ctx = await browser.newContext({
      viewport: { width, height: 900 },
      hasTouch: touch,
      isMobile: touch,
    })
    const page = await ctx.newPage()
    await login(page)
    for (const path of [
      '/scans',
      '/scans/new',
      resultUrl,
      reviewUrl,
      '/admin/rules',
      '/admin/audit',
      '/privacy',
    ]) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
      expect(overflow, `${path} scrolls sideways at ${width} px`).toBeLessThanOrEqual(0)
      if (!touch) continue
      // WCAG 2.5.8 exempts links inside a line of text; DESIGN asks 44 px for the rest.
      const small = await page.evaluate(() =>
        [
          ...document.querySelectorAll<HTMLElement>(
            'button, a, input, select, textarea, [role=button]',
          ),
        ]
          .filter((e) => e.offsetParent !== null && getComputedStyle(e).display !== 'inline')
          .filter((e) => !e.closest('article')) // marks inside the document text
          .map((e) => ({
            name: (e.getAttribute('aria-label') ?? e.textContent ?? '').trim().slice(0, 30),
            h: e.getBoundingClientRect().height,
          }))
          .filter((x) => x.h > 2 && x.h < 44),
      )
      expect(small, `${path} has small touch targets at ${width} px`).toEqual([])
    }
    await ctx.close()
  })
}
