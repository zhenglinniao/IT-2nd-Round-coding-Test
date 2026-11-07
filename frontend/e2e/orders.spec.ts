import { test, expect } from '@playwright/test';

test('source products and exact order totals appear in the browser', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle('订单工作台 · Aeris');
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await expect(page.getByRole('heading', { name: 'V22 Dispensary', exact: true })).toBeVisible();
  await expect(page.getByRole('row', { name: /TBAMET10/ })).toContainText('A$270.00');
  await expect(page.locator('.grand-total')).toContainText('A$2,147.00');
  await expect(page.locator('.rounding')).toContainText('-A$0.01');
  await expect(page.getByText('物流暂不可用', { exact: true })).toBeVisible();
  await expect(page.getByText('服务端尚未配置完整的快递查询凭据。')).toBeVisible();
  await page.screenshot({ path: '../output/playwright/order-desktop-zh.png', fullPage: true });
});

test('switching orders changes products, totals and both parcel groups', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /Cann Life Dispensary/ }).click();
  await expect(
    page.getByRole('heading', { name: 'Cann Life Dispensary', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('row', { name: /AURPUR10/ })).toContainText('A$900.00');
  await expect(page.getByRole('row', { name: /TBAMET10/ })).toHaveCount(0);
  await expect(page.locator('.grand-total')).toContainText('A$1,671.00');
  await expect(page.getByRole('article', { name: 'StarTrack 2FWZ50008645' })).toBeVisible();
  await expect(page.getByRole('article', { name: 'TNT 快递 305506914' })).toContainText(
    '服务端未启用 TNT 官方公开追踪查询。',
  );
  await expect(page).toHaveURL(/order=PO-20251203-00046/);
});

test('unknown order and no search results are recoverable', async ({ page }) => {
  await page.goto('/?order=UNKNOWN');
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByRole('button', { name: /V22 Dispensary/ }).click();
  await expect(page.getByRole('heading', { name: 'V22 Dispensary', exact: true })).toBeVisible();
  await page.getByRole('textbox', { name: '搜索订单' }).fill('no-such-order');
  await expect(page.getByText('没有匹配的订单。')).toBeVisible();
  await page.getByRole('textbox', { name: '搜索订单' }).fill('');
  await expect(page.getByRole('button', { name: /Cann Life Dispensary/ })).toBeVisible();
});

test('a synthetic courier response renders events only inside an isolated browser test', async ({
  page,
}) => {
  await page.route('**/api/orders/*/tracking', (route) =>
    route.fulfill({
      json: {
        shipments: [
          {
            id: 'track-1',
            carrier: 'startrack',
            tracking_number: '2FWZ50008569',
            query_state: 'available',
            status: 'Delivered',
            last_update: '2025-12-02T09:00:00+11:00',
            events: [
              {
                description: 'Processed at facility',
                location: 'TEST LOCATION',
                date: '2025-12-02T09:00:00+11:00',
              },
            ],
            message: 'Synthetic fixture',
            environment: 'testbed',
            fetched_at: null,
            cached: false,
          },
        ],
      },
    }),
  );
  await page.goto('/');
  await expect(page.getByText('已送达')).toBeVisible();
  await expect(page.getByText('已在处理中心处理')).toBeVisible();
  await expect(
    page.getByText('此为官方测试环境返回的测试轨迹，不代表该订单的实际运输记录。'),
  ).toBeVisible();
  await expect(page.locator('.grand-total')).toContainText('A$2,147.00');
});

test('TNT history displays Chinese events and preserves the official unzoned time', async ({
  page,
}) => {
  await page.route('**/api/orders/*/tracking', (route) =>
    route.fulfill({
      json: {
        shipments: [
          {
            id: 'track-3',
            carrier: 'tnt',
            tracking_number: '305506914',
            query_state: 'available',
            status: "We've delivered your shipment",
            last_update: null,
            last_update_text: '04/12/2025 13:00',
            events: [
              {
                description: "We've delivered your shipment",
                location: 'Melbourne - Airport',
                date: null,
                date_text: '04/12/2025 13:00',
              },
            ],
            message: 'Synthetic fixture',
            environment: 'tnt_public',
            fetched_at: null,
            cached: false,
          },
        ],
      },
    }),
  );
  await page.goto('/?order=PO-20251203-00046');
  const parcel = page.getByRole('article', { name: 'TNT 快递 305506914' });
  await expect(parcel.locator('.timeline')).toContainText('已送达');
  await expect(parcel.locator('time')).toHaveText('04/12/2025 13:00');
  await expect(parcel).toContainText('官网时间格式为日/月/年，未标注时区，按原文显示。');
  await expect(parcel).not.toContainText('测试环境');
});

test('mobile page contains horizontal scrolling inside the product table only', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?order=PO-20251203-00046');
  await expect(
    page.getByRole('heading', { name: 'Cann Life Dispensary', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('article', { name: 'TNT 快递 305506914' })).toBeVisible();
  const dimensions = await page.evaluate(() => ({
    page: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }));
  expect(dimensions.page).toBeLessThanOrEqual(dimensions.viewport);
  await page.screenshot({ path: '../output/playwright/order-mobile-zh.png', fullPage: true });
});
