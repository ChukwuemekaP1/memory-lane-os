import { expect, test } from "@playwright/test";

/**
 * Full viewing + guest journeys. These need a running API with a seeded
 * space, so they only run when PLAYWRIGHT_API_URL is set (compose e2e);
 * the default frontend CI job skips them and runs smoke.spec.ts instead.
 */
const API_URL = process.env.PLAYWRIGHT_API_URL ?? "";
const SPACE_ID = process.env.PLAYWRIGHT_SPACE_ID ?? "";
const GUEST_TOKEN = process.env.PLAYWRIGHT_GUEST_TOKEN ?? "";

test.skip(!API_URL || !SPACE_ID, "needs PLAYWRIGHT_API_URL + PLAYWRIGHT_SPACE_ID");

test("guest journey: contribute → gallery → lightbox → wall", async ({ page, request }) => {
  // Seed one guest contribution directly through the API.
  const posted = await request.post(`${API_URL}/v1/spaces/${SPACE_ID}/contributions`, {
    headers: GUEST_TOKEN ? { Authorization: `Bearer ${GUEST_TOKEN}` } : {},
    data: { kind: "message", body: `E2E hello ${Date.now()}`, guest_name: "E2E Guest" },
  });
  expect(posted.ok()).toBeTruthy();

  const guestQuery = GUEST_TOKEN ? `?guest=${GUEST_TOKEN}` : "";
  await page.goto(`/s/${SPACE_ID}${guestQuery}`);
  await expect(page.getByRole("heading").first()).toBeVisible();

  await page.goto(`/s/${SPACE_ID}/timeline${guestQuery}`);
  await expect(page.getByText("E2E Guest").first()).toBeVisible({ timeout: 15_000 });

  await page.goto(`/s/${SPACE_ID}/wall${guestQuery}`);
  await expect(page.getByText(/celebrating live|updates paused/i)).toBeVisible();

  await page.goto(`/s/${SPACE_ID}/contribute${guestQuery}`);
  await page.getByPlaceholder("Write something warm…").fill(`Wall post ${Date.now()}`);
  await page.getByPlaceholder("How should you appear?").fill("E2E Guest");
  await page.getByRole("button", { name: "Share memory" }).click();
  await expect(page.getByText(/thank you/i)).toBeVisible({ timeout: 15_000 });
});
