import { expect, test } from "@playwright/test";

test("home renders and reports API status", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /shared memory/i })).toBeVisible();
  // Either the readiness card or the unreachable notice must appear.
  await expect(page.getByText(/API(\s|ready|unreachable)/i).first()).toBeVisible({
    timeout: 15_000,
  });
});
