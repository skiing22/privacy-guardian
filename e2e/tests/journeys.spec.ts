import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import { login, REVIEW_TEXT, startScan, SURE_TEXT, waitForResult } from './helpers'

test.describe.configure({ mode: 'serial' })

let token = ''

test('J1: clean a document and download it', async ({ page }) => {
  await login(page)
  await startScan(page, SURE_TEXT)
  const sheet = await waitForResult(page)
  const cleaned = await sheet.innerText()
  for (const secret of ['Rahul Sharma', '98470 12345', 'rahul.sharma@example.com']) {
    expect(cleaned).not.toContain(secret)
  }
  token = cleaned.match(/PERSON_[0-9a-f]{6,}/)?.[0] ?? ''
  expect(token).not.toBe('')

  const [file] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('link', { name: 'Download cleaned file' }).click(),
  ])
  const body = readFileSync((await file.path()) ?? '', 'utf8')
  expect(body).toContain(token)
  expect(body).not.toContain('98470 12345')

  const [report] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('link', { name: 'Download report' }).click(),
  ])
  const json = readFileSync((await report.path()) ?? '', 'utf8')
  expect(json).not.toContain('Rahul') // the report holds no values (API 4.10)

  // the new scan is in the list
  await page.getByRole('link', { name: 'Scans', exact: true }).first().click()
  await expect(page.getByRole('link', { name: 'pasted-text.txt' }).first()).toBeVisible()
})

test('J2: answer a review by keyboard, with undo', async ({ page }) => {
  await login(page)
  await startScan(page, REVIEW_TEXT)
  const heading = page.getByRole('heading', { name: /Needs your answer: 1 of 2/ })
  await expect(heading).toBeVisible({ timeout: 30_000 })
  await page.keyboard.press('2') // keep visible ...
  await expect(page.getByText('1 of 2 answered')).toBeVisible()
  await page.keyboard.press('z') // ... no, undo
  await expect(page.getByText('0 of 2 answered')).toBeVisible()
  await page.keyboard.press('1')
  await page.keyboard.press('1')
  const submit = page.getByRole('button', { name: 'Submit answers' })
  await expect(submit).toBeFocused()
  await page.keyboard.press('Enter')
  const sheet = await waitForResult(page)
  const cleaned = await sheet.innerText()
  expect(cleaned).not.toContain('Priya')
  expect(cleaned).not.toContain('Nehru Nagar')
})

test('J3 and J4: show a real value, then catch a tampered audit log', async ({ page }) => {
  test.skip(!token, 'needs the token from J1')
  await login(page)

  // J3: show the real value behind the token, with a reason
  await page.goto('/admin/rules')
  await page.getByLabel('Token').fill(token)
  await page.getByLabel('Reason').fill('court order 2026/77')
  await page.getByRole('button', { name: 'Show value' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Show value' }).click()
  const box = page.getByRole('region', { name: 'Real value', exact: true })
  await expect(box).toContainText('Rahul Sharma')
  await box.getByRole('button', { name: 'Hide' }).click()
  await expect(box).toBeHidden()

  // J4: the log checks out and the reveal is in it, by token only
  await page.goto('/admin/audit')
  await expect(page.getByRole('row').filter({ hasText: 'Real value shown' }).first()).toContainText(
    token,
  )
  await expect(page.getByRole('table')).not.toContainText('Rahul Sharma')
  await page.getByRole('button', { name: 'Save anchor' }).click()
  await expect(page.getByText(/Anchor saved at record/)).toBeVisible()
  await page.getByRole('button', { name: 'Verify log' }).click()
  await expect(page.getByText(/records check out and match the anchor/)).toBeVisible()

  const db = process.env.E2E_DB
  test.skip(!db, 'set E2E_DB to the app.db path to run the tamper step')
  execFileSync('python3', ['tamper.py', db ?? '', '1'], { cwd: new URL('..', import.meta.url) })
  await page.getByRole('button', { name: 'Verify log' }).click()
  await expect(page.getByText('Record 1 was changed after it was saved.')).toBeVisible()
  const row = page.getByRole('row', { name: 'Record 1, changed after it was saved' })
  await expect(row).toBeInViewport()
})

test('logging out ends the session', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: /Account menu/ }).click()
  await page.getByRole('button', { name: 'Log out' }).click()
  await page.waitForURL('**/login')
  await page.goto('/scans')
  await page.waitForURL(/\/login\?next=%2Fscans/)
})
