// Optional real-browser regression: PLAYWRIGHT_MODULE and CHROMIUM_PATH can
// point to installed tooling; no production dependency or test-clock hook.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const assert = require('node:assert/strict');

(async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'midnight-'));
  const port = 18761;
  let server, browser;
  try {
    fs.mkdirSync(path.join(temp, 'data'));
    fs.copyFileSync(path.join(__dirname, 'app.py'), path.join(temp, 'app.py'));
    fs.copyFileSync(path.join(__dirname, 'data/sample_reviews.csv'),
      path.join(temp, 'data/sample_reviews.csv'));
    const clock = path.join(temp, 'clock');
    fs.writeFileSync(clock, '2026-01-02T04:59:59+00:00');
    fs.writeFileSync(path.join(temp, 'harness.py'), `
import runpy
from pathlib import Path
from datetime import datetime
import action_tracker as A
import engine as E
from dataset_store import SAMPLE_ID
ROOT = Path(__file__).parent
real_today = getattr(A, "_test_original_today", A.restaurant_today)
A._test_original_today = real_today
A.restaurant_today = lambda zone=A.DEFAULT_RESTAURANT_TIMEZONE: real_today(
    zone, now=datetime.fromisoformat((ROOT / "clock").read_text()))
location = E.load_reviews(ROOT / "data/sample_reviews.csv").iloc[0]["location"]
fixture = dict(dataset_tag=SAMPLE_ID, action_id="midnight", location=location,
    theme="Service speed", status="Planned", start_date="2026-01-01",
    due_date="2026-01-01", action_text="Check handoffs.", owner="Original owner")
A.load_actions = lambda *args, **kwargs: [fixture.copy()]
runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
`);
    server = spawn('uv', ['run', 'python', '-m', 'streamlit', 'run',
      path.join(temp, 'harness.py'), '--server.port', String(port),
      '--server.address', '127.0.0.1', '--server.headless', 'true',
      '--browser.gatherUsageStats', 'false'], {
      cwd: path.dirname(__dirname),
      env: { ...process.env, PYTHONPATH: __dirname }, stdio: ['ignore', 'pipe', 'pipe']
    });
    let logs = '';
    server.stdout.on('data', d => { logs += d; });
    server.stderr.on('data', d => { logs += d; });
    for (let i = 0; i < 60; i++) {
      try { if ((await fetch(`http://127.0.0.1:${port}/_stcore/health`)).ok) break; }
      catch {}
      if (i === 59) throw new Error(`Harness failed: ${logs}`);
      await new Promise(r => setTimeout(r, 500));
    }
    browser = await chromium.launch({
      executablePath: process.env.CHROMIUM_PATH || undefined,
      headless: true, args: ['--no-sandbox']
    });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    await page.goto(`http://127.0.0.1:${port}`);
    await page.getByRole('tab', { name: /Action tracker/i }).click({ timeout: 60000 });
    await page.getByText('Overdue only', { exact: true }).click();
    await page.getByText(/No overdue action plans/).waitFor();
    await page.getByText(/Edit .*Service speed.*Original owner/).click();
    const form = page.locator('[data-testid="stForm"]').filter({
      has: page.getByRole('button', { name: 'Save updates', exact: true })
    });
    await form.getByLabel('Manager action', { exact: true }).fill('Unsaved midnight draft');
    await form.getByLabel('Owner (optional)', { exact: true }).fill('Night manager draft');
    const dates = form.locator('[data-testid="stDateInput"] input');
    await dates.nth(0).fill('2025-12-30');
    await dates.nth(0).press('Tab');
    await dates.nth(1).fill('2026-01-03');
    await dates.nth(1).press('Tab');
    const inputs = () => form.locator('input, textarea').evaluateAll(
      elements => elements.map(e => ({ value: e.value, role: e.getAttribute('role') })));
    const before = await inputs();
    const statusBefore = await form.getByRole('combobox').inputValue();
    assert.equal(statusBefore, 'Planned');
    fs.writeFileSync(clock, '2026-01-02T05:00:01+00:00');
    // No browser interaction until the timer has produced the new warning.
    await page.getByText('Overdue — this active action is past its due date.')
      .waitFor({ timeout: 45000 });
    await page.getByText(/Showing 1 of 1 action plans/).waitFor();
    assert.deepEqual(await inputs(), before, 'Timer changed unsent input');
    assert.equal(await form.getByRole('combobox').inputValue(), statusBefore);
    await page.getByText('Location calendars', { exact: true }).click();
    assert.match(await page.locator('[data-testid="stSidebar"]').innerText(),
      /Action calendar: 2026-01-02/);
    await page.getByRole('tab', { name: /Export/i }).click();
    const summary = page.locator('[data-testid="stCode"]');
    await summary.filter({ hasText: 'OVERDUE' }).waitFor();
    const summaryBefore = await summary.allTextContents();
    await page.waitForTimeout(32000);
    assert.deepEqual(await summary.allTextContents(), summaryBefore, 'Summary duplicated');
    await page.getByRole('tab', { name: /Action tracker/i }).click();
    assert.deepEqual(await inputs(), before);
    assert.equal(await form.getByRole('combobox').inputValue(), statusBefore);
    if (process.env.MIDNIGHT_SCREENSHOT) {
      await page.screenshot({ path: process.env.MIDNIGHT_SCREENSHOT, fullPage: true });
    }
    assert.equal(await page.locator('[data-testid="stException"]').count(), 0);
    console.log('PASS: local midnight updates filter, warning, calendar and summary; '
      + 'unsaved action, owner, status and dates survive two timer cycles.');
  } finally {
    if (browser) await browser.close();
    if (server) server.kill('SIGTERM');
    fs.rmSync(temp, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
