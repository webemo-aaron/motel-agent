import { test, expect } from '@playwright/test';

function isoDay(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
}

async function unlockAdmin(page: any) {
  await page.getByText('Staff/Admin Access').click();
  await page.getByPlaceholder('Enter PIN').fill('2468');
  await page.getByRole('button', { name: 'Unlock' }).click();
  await expect(page.getByTestId('admin-sidebar')).toBeVisible();
  await expect(page.getByText('Admin Navigation')).toBeVisible();
  await expect(page.getByTestId('admin-topbar')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Operations' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Desk Overview' })).toBeVisible();

  await expect(page.getByTestId('nav-frontdesk-links')).toBeVisible();
  await expect(page.getByTestId('nav-management-links')).toBeVisible();
  await page.getByTestId('nav-group-frontdesk').getByRole('button', { name: /Front Desk/ }).click();
  await expect(page.getByTestId('nav-frontdesk-links')).toBeHidden();
  await page.getByTestId('nav-group-frontdesk').getByRole('button', { name: /Front Desk/ }).click();
  await expect(page.getByTestId('nav-frontdesk-links')).toBeVisible();
}

test('kiosk home loads and default dates are set', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Welcome to West Bethel Motel' })).toBeVisible();
  await expect(page.getByText('Get a Room')).toBeVisible();
  await expect(page.getByText('Contact Operator')).toBeVisible();
  await expect(page.getByText(/auto-resets after inactivity/i)).toBeVisible();
  await expect(page.getByLabel('Booking arrival date')).toHaveValue(isoDay(0));
  await expect(page.getByLabel('Departure date')).toHaveValue(isoDay(1));
  await page.getByRole('button', { name: 'Find Reservation' }).click();
  await expect(page.getByLabel('Lookup arrival date')).toHaveValue(isoDay(0));
});

test('admin unlock and desk loads', async ({ page }) => {
  await page.goto('/');
  await unlockAdmin(page);
  await expect(page.getByRole('link', { name: 'Manager Portal' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Revenue and Rates' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Advertising and Campaigns' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Events' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Groups and Leads' })).toBeVisible();
});

test('manager and rates render after unlock', async ({ page }) => {
  await page.goto('/');
  await unlockAdmin(page);
  await page.goto('/manager');
  await expect(page.getByText('Immediate Actions')).toBeVisible();
  await expect(page.getByText('Manager Submenu')).toBeVisible();
  const managerMenu = page.locator('section', { hasText: 'Manager Submenu' });
  await managerMenu.getByRole('link', { name: 'Advertising and Campaigns' }).click();
  await expect(page).toHaveURL(/#campaigns/);
  await managerMenu.getByRole('link', { name: 'Events' }).click();
  await expect(page).toHaveURL(/#events/);
  await expect(page.getByText('Events Workspace')).toBeVisible();
  await managerMenu.getByRole('link', { name: 'Groups and Leads' }).click();
  await expect(page).toHaveURL(/#groups/);
  await expect(page.getByText('Groups & Leads Workspace')).toBeVisible();
  await expect(page.getByText('Campaign Planner')).toBeVisible();
  await expect(page.getByText('Advertising & Campaigns Workspace')).toBeVisible();
  await expect(page.getByText('Integrations: Telegram')).toBeVisible();
  await page.goto('/rates');
  await expect(page.getByRole('heading', { name: 'Rate Intelligence' })).toBeVisible();
  await expect(page.getByTestId('rate-ops-panel')).toBeVisible();
  await expect(page.getByText('Operational Controls')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Refresh now' })).toBeVisible();
  await expect(page.getByRole('button', { name: /auto refresh/i })).toBeVisible();
  await expect(page.getByTestId('rate-recommendations-panel')).toBeVisible();
  await page.getByLabel('SQ Base').fill('115');
  await page.getByLabel('Lead Window').selectOption('14+ days');
  await page.getByLabel('Weekend Mode').uncheck();
  await expect(page.getByRole('button', { name: 'Publish suggested rates' })).toBeVisible();
  await expect(page.getByText('Top Competitor Signals')).toBeVisible();
  await expect(page.getByLabel('Timeframe')).toBeVisible();
  await page.getByLabel('Timeframe').selectOption('90d');
  await page.getByLabel('Confidence').selectOption('high_only');
  await expect(page.getByText('Portal QA Summary (24h)')).toBeVisible();
});
