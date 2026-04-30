import { test as setup, expect } from '@playwright/test';

const authFile = 'e2e/.auth/user.json';

setup('authenticate', async ({ page }) => {
  await page.goto('/login');
  await page.fill('input[type="email"]', 'admin@workspace.ai');
  await page.fill('input[type="password"]', 'admin@workspace.ai');
  await page.click('button[type="submit"]');
  await page.waitForURL('/licenses');
  await expect(page.getByRole('heading', { name: 'License' }).first()).toBeVisible();
  await page.context().storageState({ path: authFile });
});
