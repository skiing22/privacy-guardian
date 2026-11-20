import { expect, type Page } from '@playwright/test'

export const ADMIN = {
  email: process.env.ADMIN_EMAIL ?? 'admin@example.com',
  password: process.env.ADMIN_PASSWORD ?? 'e2e-admin-password',
}

/** Keyboard only: type, then Enter (DESIGN 11). */
export async function login(page: Page, who = ADMIN) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(who.email)
  await page.getByLabel('Password').fill(who.password)
  await page.keyboard.press('Enter')
  await page.waitForURL('**/scans')
}

export async function startScan(page: Page, text: string): Promise<string> {
  await page.goto('/scans/new')
  await page.getByLabel('Or paste text').fill(text)
  await page.getByRole('button', { name: 'Start scan' }).click()
  await page.waitForURL(/\/scans\/[0-9a-f-]{36}$/)
  return page.url()
}

export async function waitForResult(page: Page) {
  const sheet = page.getByRole('article', { name: 'Cleaned document' })
  await expect(sheet).toBeVisible({ timeout: 30_000 })
  return sheet
}

/** J1 text: everything is found with certainty, so no review. */
export const SURE_TEXT =
  'Discharge summary. Patient Rahul Sharma, phone 98470 12345, email rahul.sharma@example.com.'
/** J2 text: "Priya" and "Nehru Nagar" are unsure, so the scan pauses for review. */
export const REVIEW_TEXT =
  'Please thank Priya for sending the documents to 22, Nehru Nagar. Call 98470 12345.'
