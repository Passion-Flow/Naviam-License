import { test, expect } from '@playwright/test';

const BASE = 'http://127.0.0.1:3000';

function parseTabCount(text: string): number {
  const match = text.match(/\((\d+)\)/);
  return match?.[1] ? Number.parseInt(match[1], 10) : 0;
}

test.describe('License Manager E2E', () => {
  test('licenses page loads with action buttons', async ({ page }) => {
    await page.goto(`${BASE}/licenses`);
    await expect(page.getByRole('heading', { name: 'License' }).first()).toBeVisible();
    await expect(page.locator('text=签发、续期、吊销 License 文件')).toBeVisible();

    await page.waitForSelector('table tbody tr');
    const rows = page.locator('table tbody tr');
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);

    const firstRow = rows.first();
    const statusCell = firstRow.locator('td').nth(3);
    const statusText = await statusCell.textContent();

    if (statusText && !statusText.includes('吊销') && !statusText.includes('失效')) {
      await expect(firstRow.locator('button[title="续期"]')).toBeVisible();
      await expect(firstRow.locator('button[title="吊销"]')).toBeVisible();
    }
    await expect(firstRow.locator('button[title="删除"]')).toBeVisible();
  });

  test('audit page shows human-readable events', async ({ page }) => {
    await page.goto(`${BASE}/audit`);
    await expect(page.getByRole('heading', { name: '审计日志' })).toBeVisible();
    await page.waitForSelector('table tbody tr');
    const rows = page.locator('table tbody tr');
    expect(await rows.count()).toBeGreaterThan(0);

    // 操作列（第3列）应包含中文描述，如"签发 License"、"登录系统"等
    const actions = await page.locator('table tbody tr td:nth-child(3)').allTextContents();
    const hasReadableAction = actions.some(a => a.includes('License') || a.includes('登录') || a.includes('客户') || a.includes('产品'));
    expect(hasReadableAction).toBe(true);

    // 操作人列（第2列）应包含用户名或系统
    const actors = await page.locator('table tbody tr td:nth-child(2)').allTextContents();
    const hasActor = actors.some(a => a.includes('admin') || a.includes('系统'));
    expect(hasActor).toBe(true);
  });

  test('audit detail modal shows full event info', async ({ page }) => {
    await page.goto(`${BASE}/audit`);
    await expect(page.getByRole('heading', { name: '审计日志' })).toBeVisible();
    await page.waitForSelector('table tbody tr');

    // Click first row
    await page.locator('table tbody tr').first().click();

    // Detail modal should show hash chain, signature, payload
    await expect(page.getByRole('heading', { name: '审计事件详情' })).toBeVisible();
    await expect(page.locator('text=哈希链（不可篡改）')).toBeVisible();
    await expect(page.locator('text=数字签名')).toBeVisible();
    await expect(page.locator('text=操作载荷 (Payload)')).toBeVisible();

    // Close modal by pressing Escape
    await page.keyboard.press('Escape');
    await expect(page.getByRole('heading', { name: '审计事件详情' })).toBeHidden();
  });

  test('customers page has edit/delete buttons', async ({ page }) => {
    await page.goto(`${BASE}/customers`);
    await expect(page.getByRole('heading', { name: '客户' })).toBeVisible();
    await page.waitForSelector('table tbody tr');
    const rows = page.locator('table tbody tr');
    expect(await rows.count()).toBeGreaterThan(0);

    const firstRow = rows.first();
    await expect(firstRow.locator('button[title="编辑"]')).toBeVisible();
    await expect(firstRow.locator('button[title="删除"]')).toBeVisible();
  });

  test('products page has create/edit/delete', async ({ page }) => {
    await page.goto(`${BASE}/products`);
    await expect(page.getByRole('heading', { name: '产品' })).toBeVisible();
    await expect(page.locator('button:has-text("新增产品")')).toBeVisible();
    await page.waitForSelector('table tbody tr');
    const rows = page.locator('table tbody tr');
    expect(await rows.count()).toBeGreaterThan(0);

    const firstRow = rows.first();
    await expect(firstRow.locator('button[title="编辑"]')).toBeVisible();
    await expect(firstRow.locator('button[title="删除"]')).toBeVisible();
  });

  test('license renew flow', async ({ page }) => {
    await page.goto(`${BASE}/licenses`);
    await page.waitForSelector('table tbody tr');

    const renewButtons = page.locator('button[title="续期"]');
    const renewCount = await renewButtons.count();
    test.skip(renewCount === 0, 'No renewable licenses found');

    await renewButtons.first().click();

    await expect(page.getByRole('heading', { name: '续期 License' })).toBeVisible();

    const futureDate = new Date();
    futureDate.setFullYear(futureDate.getFullYear() + 1);
    const dateStr = futureDate.toISOString().slice(0, 16);
    await page.fill('input[type="datetime-local"]', dateStr);

    await page.click('button:has-text("确认续期")');

    // Success state appears in same modal; click 关闭 to dismiss
    await expect(page.locator('text=续期成功')).toBeVisible();
    await page.click('button:has-text("关闭")');

    await expect(page.getByRole('heading', { name: '续期 License' })).toBeHidden();
    await expect(page.getByRole('heading', { name: 'License' }).first()).toBeVisible();
  });

  test('customer edit flow', async ({ page }) => {
    await page.goto(`${BASE}/customers`);
    await page.waitForSelector('table tbody tr');

    const editButtons = page.locator('button[title="编辑"]');
    const editCount = await editButtons.count();
    test.skip(editCount === 0, 'No editable customers found');

    await editButtons.first().click();

    await expect(page.getByRole('heading', { name: '编辑客户' })).toBeVisible();

    const inputs = page.locator('input[type="text"]');
    await expect(inputs.first()).toBeVisible();
    const currentName = await inputs.first().inputValue();
    await inputs.first().fill(currentName + '_test');

    await page.click('button:has-text("保存修改")');

    await expect(page.getByRole('heading', { name: '编辑客户' })).toBeHidden();
    await expect(page.getByRole('heading', { name: '客户' })).toBeVisible();
  });

  test('notifications page - mark read and delete work correctly', async ({ page }) => {
    await page.goto(`${BASE}/notifications`);
    await expect(page.getByRole('heading', { name: '通知中心' })).toBeVisible();

    // Wait for loading to finish
    await page.waitForFunction(() => {
      return document.querySelector('.animate-spin') === null;
    }, { timeout: 10000 });

    // Capture initial counts from tab labels (e.g. "全部 (7)", "未读 (5)")
    // Scoped to filter tab container to avoid matching "全部已读" button
    const filterTabs = page.locator('div.flex.items-center.gap-1 > button');
    const allTab = filterTabs.filter({ hasText: /全部/ });
    const unreadTab = filterTabs.filter({ hasText: /未读/ });

    const allTabText = await allTab.textContent() || '';
    const unreadTabText = await unreadTab.textContent() || '';

    const initialTotal = parseTabCount(allTabText);
    const initialUnread = parseTabCount(unreadTabText);

    // Skip if no notifications at all
    if (initialTotal === 0) {
      await expect(page.locator('text=暂无通知')).toBeVisible();
      return;
    }

    // Bug fix verification 1: "全部" tab count should not change when switching filter
    await unreadTab.click();
    await page.waitForTimeout(300); // let React render
    // Switch back to all
    await allTab.click();
    await page.waitForTimeout(300);
    const allTabTextAfter = await allTab.textContent() || '';
    const totalAfterSwitch = parseTabCount(allTabTextAfter);
    expect(totalAfterSwitch).toBe(initialTotal);

    // Bug fix verification 2: In unread filter, mark-as-read should remove item immediately
    if (initialUnread > 0) {
      await unreadTab.click();
      await page.waitForTimeout(300);

      const itemsBefore = await page.locator('.surface .divide-y > div').count();
      expect(itemsBefore).toBeGreaterThan(0);

      // Capture sidebar badge before mark-read (badge span has rounded-full class)
      const sidebarBadgeLocator = page.locator('nav a[href="/notifications"] span[class*="rounded-full"]');
      const sidebarBadgeBefore = await sidebarBadgeLocator.textContent().catch(() => null);
      const sidebarCountBefore = sidebarBadgeBefore ? parseInt(sidebarBadgeBefore, 10) : 0;

      // Click mark-as-read on first item
      const markReadBtn = page.locator('button[title="标记已读"]').first();
      await markReadBtn.click();

      // Item should disappear from unread list
      await page.waitForFunction((prevCount: number) => {
        return document.querySelectorAll('button[title="标记已读"]').length === 0
          || document.querySelectorAll('.surface .divide-y > div').length < prevCount;
      }, itemsBefore, { timeout: 5000 });

      const itemsAfter = await page.locator('.surface .divide-y > div').count();
      expect(itemsAfter).toBeLessThan(itemsBefore);

      // Unread tab count should decrease
      const unreadTextAfter = await unreadTab.textContent() || '';
      const unreadAfterMark = parseTabCount(unreadTextAfter);
      expect(unreadAfterMark).toBeLessThan(initialUnread);

      // Sidebar badge should decrease in real-time (via custom event)
      await page.waitForTimeout(500); // let API round-trip finish
      if (sidebarCountBefore > 0) {
        const sidebarBadgeAfter = await sidebarBadgeLocator.textContent().catch(() => null);
        const sidebarCountAfter = sidebarBadgeAfter ? parseInt(sidebarBadgeAfter, 10) : 0;
        expect(sidebarCountAfter).toBeLessThan(sidebarCountBefore);
      }
    }

    // Bug fix verification 3: Delete should reduce total count
    await allTab.click();
    await page.waitForTimeout(300);
    const itemsBeforeDelete = await page.locator('.surface .divide-y > div').count();
    if (itemsBeforeDelete > 0) {
      const deleteBtn = page.locator('button[title="删除"]').first();
      await deleteBtn.click();
      await page.waitForTimeout(300);
      const itemsAfterDelete = await page.locator('.surface .divide-y > div').count();
      expect(itemsAfterDelete).toBeLessThan(itemsBeforeDelete);

      const allTextAfterDelete = await allTab.textContent() || '';
      const totalAfterDelete = parseTabCount(allTextAfterDelete);
      expect(totalAfterDelete).toBeLessThan(initialTotal);
    }
  });

  test('settings page shows profile and login history', async ({ page }) => {
    await page.goto(`${BASE}/settings`);
    await expect(page.getByRole('heading', { name: '设置' })).toBeVisible();

    // Profile section
    await expect(page.locator('text=账号基本信息')).toBeVisible();
    await expect(page.locator('text=admin@workspace.ai').first()).toBeVisible();

    // Security section
    await expect(page.locator('text=密码策略')).toBeVisible();
    await expect(page.locator('text=两步验证 (TOTP)')).toBeVisible();

    // Login history section
    await expect(page.locator('text=登录历史').first()).toBeVisible();

    // Test change password modal opens
    await page.click('button:has-text("修改密码")');
    await expect(page.getByRole('heading', { name: '修改密码' })).toBeVisible();

    // Fill in password fields
    await page.fill('input[type="password"]', 'wrongpassword');
    await page.locator('input[type="password"]').nth(1).fill('newpassword123');
    await page.locator('input[type="password"]').nth(2).fill('newpassword123');
    await page.click('button:has-text("确认修改")');

    // Should show some error (wrong old password)
    await expect(page.locator('text=请求失败, 旧密码不正确').or(page.locator('text=请求失败'))).toBeVisible();

    // Close modal
    await page.keyboard.press('Escape');
    await expect(page.getByRole('heading', { name: '修改密码' })).toBeHidden();
  });
});
