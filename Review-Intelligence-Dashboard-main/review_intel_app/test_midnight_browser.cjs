// Isolated real-browser regression for the live overdue refresh/draft journey.
// The temporary Streamlit wrapper controls only this test process's clock;
// production app code gets no clock/auth hook. Login uses a temporary manager
// DB and the built-in synthetic dataset. Requires Playwright + Chromium.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const assert = require('node:assert/strict');
const net = require('node:net');

const repo = path.resolve(__dirname, '..');
const username = 'midnight-regression-manager';
const password = 'synthetic-test-password-only';
const sampleId = 'builtin:synthetic-sample';
const beforeMidnight = '2026-01-02T04:59:59+00:00';
const afterMidnight = '2026-01-02T05:00:01+00:00';
const yesterday = '2026-01-01';
const today = '2026-01-02';

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: repo, encoding: 'utf8', ...options
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(' ')} failed:\n${result.stderr || result.stdout}`);
  }
  return result.stdout.trim();
}

async function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(error => error ? reject(error) : resolve(port));
    });
  });
}

async function waitForText(page, text, timeout = 30000) {
  await page.getByText(text, { exact: false }).first().waitFor({ state: 'visible', timeout });
}

async function componentText(page, label) {
  for (const frame of page.frames()) {
    try {
      const text = await frame.locator('body').innerText({ timeout: 1000 });
      if (text.includes(`${label} last updated:`)) return text;
    } catch {}
  }
  return '';
}

async function waitForComponent(page, label, predicate, timeout = 90000) {
  const until = Date.now() + timeout;
  while (Date.now() < until) {
    const text = await componentText(page, label);
    if (text && predicate(text)) return text;
    await page.waitForTimeout(500);
  }
  throw new Error(`Timed out waiting for ${label}; latest text: ${await componentText(page, label)}`);
}

(async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'review-intel-midnight-'));
  const port = await freePort();
  const screenshot = process.env.MIDNIGHT_SCREENSHOT
    || path.join(os.tmpdir(), 'review-intel-midnight.png');
  let server, browser, browserContext, freshContext, logs = '';
  try {
    const dataDir = path.join(temp, 'data');
    fs.mkdirSync(dataDir, { recursive: true });
    for (const file of fs.readdirSync(__dirname).filter(name => name.endsWith('.py'))) {
      fs.copyFileSync(path.join(__dirname, file), path.join(temp, file));
    }
    fs.copyFileSync(path.join(__dirname, 'data/sample_reviews.csv'),
      path.join(dataDir, 'sample_reviews.csv'));
    fs.mkdirSync(path.join(dataDir, 'uploads'), { recursive: true });
    const rows = fs.readFileSync(path.join(dataDir, 'sample_reviews.csv'), 'utf8')
      .split(/\r?\n/);
    const location = rows[1].split(',')[1].replace(/^"|"$/g, '');
    const clock = path.join(temp, 'clock');
    fs.writeFileSync(clock,
      process.env.MIDNIGHT_EXPORT_ONLY === '1' ? afterMidnight : beforeMidnight);
    const actionLog = path.join(dataDir, 'action_log.json');
    fs.writeFileSync(actionLog, JSON.stringify([{
      dataset_tag: sampleId,
      action_id: 'synthetic-midnight-action',
      location,
      theme: 'Service speed',
      status: 'Planned',
      start_date: '2025-12-29',
      due_date: yesterday,
      action_text: 'Synthetic baseline action',
      owner: 'Synthetic baseline owner',
      created_on: '2026-01-01T00:00:00+00:00'
    }], null, 2));

    // This wrapper overrides restaurant_today only in the throwaway process
    // by passing an aware instant to the normal production calculation.
    fs.writeFileSync(path.join(temp, 'harness.py'), `
import runpy
from pathlib import Path
from datetime import datetime
import action_tracker as A
ROOT = Path(__file__).parent
real_today = getattr(A, "_test_original_today", A.restaurant_today)
A._test_original_today = real_today
def controlled_today(zone=A.DEFAULT_RESTAURANT_TIMEZONE, *, now=None):
    instant = now or datetime.fromisoformat((ROOT / "clock").read_text())
    return real_today(zone, now=instant)
A.restaurant_today = controlled_today
runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
`);
    const env = { ...process.env, PYTHONPATH: temp };
    run('uv', ['run', 'python', '-c', `
import manager_identity
manager_identity.set_account(${JSON.stringify(username)}, ${JSON.stringify(password)},
    {${JSON.stringify(sampleId)}: [${JSON.stringify(location)}]})
assert manager_identity.authenticate(${JSON.stringify(username)}, ${JSON.stringify(password)})
`], { env });

    server = spawn('uv', ['run', 'python', '-m', 'streamlit', 'run',
      path.join(temp, 'harness.py'), '--server.port', String(port),
      '--server.address', '127.0.0.1', '--server.baseUrlPath', 'dashboard',
      '--server.headless', 'true', '--browser.gatherUsageStats', 'false'], {
      cwd: repo, env, stdio: ['ignore', 'pipe', 'pipe']
    });
    server.stdout.on('data', data => { logs += data; });
    server.stderr.on('data', data => { logs += data; });
    for (let i = 0; i < 60; i++) {
      try {
        if ((await fetch(`http://127.0.0.1:${port}/dashboard/_stcore/health`)).ok) break;
      } catch {}
      if (i === 59) throw new Error(`Temporary dashboard failed to start:\n${logs}`);
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    browser = await chromium.launch({
      executablePath: process.env.CHROMIUM_PATH || undefined,
      headless: true, args: ['--no-sandbox']
    });
    browserContext = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    const page = await browserContext.newPage();
    await page.goto(`http://127.0.0.1:${port}/dashboard/`);
    await page.getByLabel('Manager ID').fill(username);
    await page.getByLabel('Manager report password').fill(password);
    await page.getByRole('button', { name: 'Unlock restaurant dashboard' }).click();
    await page.waitForTimeout(1200);
    if (process.env.MIDNIGHT_EXPORT_ONLY === '1') {
      await page.getByRole('tab', { name: /Export/i }).click();
      const summary = page.locator('[data-testid="stCode"]');
      await summary.filter({ hasText: 'OVERDUE' }).waitFor({ state: 'visible', timeout: 30000 });
      const summaryText = await summary.innerText();
      assert.match(summaryText, /OVERDUE.*Synthetic baseline owner/s);
      await page.screenshot({ path: screenshot.replace(/\.png$/i, '-export-smoke.png'), fullPage: true });
      console.log('PASS: targeted Export-tab owner-summary browser check:', summaryText);
      return;
    }
    await page.getByRole('tab', { name: /Action tracker/i }).waitFor({ state: 'visible' });

    await page.getByText('Location calendars', { exact: true }).click();
    await waitForText(page, `Action calendar: ${yesterday} · America/New_York`);
    await page.getByRole('tab', { name: /Action tracker/i }).click();
    await page.getByText('Overdue only', { exact: true }).click();
    await waitForText(page, 'No overdue action plans for this dataset');
    await page.getByText(
      new RegExp(`Edit ${location}: Service speed · Synthetic baseline owner`)
    ).click();
    const textBox = page.getByLabel('Manager action', { exact: true });
    const ownerBox = page.getByLabel('Owner (optional)', { exact: true });
    await textBox.fill('Unsaved reconnect draft — synthetic only');
    await ownerBox.fill('Unsaved reconnect owner');
    await ownerBox.press('Tab');
    const draft = { action: await textBox.inputValue(), owner: await ownerBox.inputValue() };
    const savedActionBytes = fs.readFileSync(actionLog);
    const oldActionStatus = await waitForComponent(
      page, 'Action status', text => /Updated recently/.test(text), 30000);
    const oldActionStamp = oldActionStatus.match(/Action status last updated: (.+)/)[1];
    const oldCalendar = await waitForComponent(
      page, 'Restaurant calendar', text => /Updated recently/.test(text), 30000);
    const oldCalendarStamp = oldCalendar.match(/Restaurant calendar last updated: (.+)/)[1];
    const oldOwner = await waitForComponent(
      page, 'Owner summary', text => /Updated recently/.test(text), 30000);
    const oldOwnerStamp = oldOwner.match(/Owner summary last updated: (.+)/)[1];
    assert.doesNotMatch(oldOwner, /OVERDUE/);
    assert.match(await page.locator('body').innerText(),
      /If the session is lost, unsaved drafts cannot be recovered/);

    // Disconnect the real browser context. The embedded watchdog must warn,
    // while all server-rendered timestamps and action data remain unchanged.
    await browserContext.setOffline(true);
    await waitForComponent(page, 'Action status', text => /Updates may be stale/.test(text), 5000);
    await page.waitForTimeout(1200);
    const staleAction = await componentText(page, 'Action status');
    assert.match(staleAction, /Copy unsaved text before reloading or signing in again/);
    const disconnectedActionStamp =
      staleAction.match(/Action status last updated: (.+)/)[1];
    const disconnectedCalendarStamp = (await componentText(page, 'Restaurant calendar'))
      .match(/Restaurant calendar last updated: (.+)/)[1];
    const disconnectedOwner = await componentText(page, 'Owner summary');
    const disconnectedOwnerStamp =
      disconnectedOwner.match(/Owner summary last updated: (.+)/)[1];
    assert.doesNotMatch(await componentText(page, 'Owner summary'), /OVERDUE/);
    assert.deepEqual(fs.readFileSync(actionLog), savedActionBytes);
    await page.waitForTimeout(1200);
    assert.equal((await componentText(page, 'Action status'))
      .match(/Action status last updated: (.+)/)[1], disconnectedActionStamp);
    assert.equal((await componentText(page, 'Restaurant calendar'))
      .match(/Restaurant calendar last updated: (.+)/)[1], disconnectedCalendarStamp);
    assert.equal((await componentText(page, 'Owner summary'))
      .match(/Owner summary last updated: (.+)/)[1], disconnectedOwnerStamp);
    await page.screenshot({
      path: screenshot.replace(/\.png$/i, '-offline.png'), fullPage: true
    });

    // Move the temporary app clock across restaurant midnight while offline.
    // The normal 30-second fragments must refresh after the same session
    // reconnects; no interaction is used to force a server rerun.
    fs.writeFileSync(clock, afterMidnight);
    await page.waitForTimeout(1200);
    assert.equal((await componentText(page, 'Action status'))
      .match(/Action status last updated: (.+)/)[1], disconnectedActionStamp);
    assert.deepEqual(fs.readFileSync(actionLog), savedActionBytes);
    await browserContext.setOffline(false);
    await page.waitForFunction(() => navigator.onLine, null, { timeout: 10000 });

    const freshAction = await waitForComponent(page, 'Action status', text =>
      /Updated recently/.test(text) &&
      text.match(/Action status last updated: (.+)/)?.[1] !== disconnectedActionStamp, 90000);
    const freshCalendar = await waitForComponent(page, 'Restaurant calendar', text =>
      /Updated recently/.test(text) &&
      text.match(/Restaurant calendar last updated: (.+)/)?.[1] !== disconnectedCalendarStamp, 90000);
    await waitForText(page, `Action calendar: ${today} · America/New_York`, 90000);
    await waitForText(page, 'Showing 1 of 1 action plans');
    await waitForText(page, 'Overdue — this active action is past its due date.');
    assert.equal(await textBox.inputValue(), draft.action);
    assert.equal(await ownerBox.inputValue(), draft.owner);
    assert.deepEqual(fs.readFileSync(actionLog), savedActionBytes,
      'the independent widgets must remain unsaved after refresh');
    await page.screenshot({
      path: screenshot.replace(/\.png$/i, '-action.png'), fullPage: true
    });

    await page.getByRole('tab', { name: /Export/i }).click();
    const freshOwner = await waitForComponent(page, 'Owner summary', text =>
      /Updated recently/.test(text) &&
      text.match(/Owner summary last updated: (.+)/)?.[1] !== disconnectedOwnerStamp, 90000);
    const ownerSummary = page.locator('[data-testid="stCode"]');
    await ownerSummary.filter({ hasText: 'OVERDUE' }).waitFor({ state: 'visible', timeout: 30000 });
    assert.match(await ownerSummary.innerText(), /OVERDUE.*Synthetic baseline owner/s);
    assert.match(freshOwner, /Owner summary last updated:/);

    // The page-level lost-session guidance plus a separate fresh browser
    // session verifies that temporary widget drafts are not persisted. This
    // does not wait for the 30-minute session expiry duration.
    await page.screenshot({ path: screenshot, fullPage: true });
    freshContext = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    const freshPage = await freshContext.newPage();
    await freshPage.goto(`http://127.0.0.1:${port}/dashboard/`);
    await freshPage.getByLabel('Manager ID').fill(username);
    await freshPage.getByLabel('Manager report password').fill(password);
    await freshPage.getByRole('button', { name: 'Unlock restaurant dashboard' }).click();
    await freshPage.getByRole('tab', { name: /Action tracker/i }).click();
    await waitForText(freshPage, 'If the session is lost, unsaved drafts cannot be recovered');
    await freshPage.getByText(
      new RegExp(`Edit ${location}: Service speed · Synthetic baseline owner`)
    ).click();
    assert.equal(await freshPage.getByLabel('Manager action', { exact: true }).inputValue(),
      'Synthetic baseline action');
    assert.equal(await freshPage.getByLabel('Owner (optional)', { exact: true }).inputValue(),
      'Synthetic baseline owner');
    await freshPage.screenshot({
      path: screenshot.replace(/\.png$/i, '-new-session.png'), fullPage: true
    });
    assert.equal(await page.locator('[data-testid="stException"]').count(), 0);
    console.log(`PASS: /dashboard same-session offline/reconnect across New York midnight. `
      + `Stale warning held at ${oldActionStamp}; after reconnect, action/calendar/owner `
      + `last-updated timestamps advanced and overdue state appeared; unsaved action/owner `
      + `survived but were not saved. Fresh-session guidance/baseline also verified. `
      + `Screenshots: ${screenshot.replace(/\.png$/i, '-offline.png')}, `
      + `${screenshot.replace(/\.png$/i, '-action.png')}, ${screenshot}, `
      + `${screenshot.replace(/\.png$/i, '-new-session.png')}`);
  } finally {
    if (freshContext) await freshContext.close();
    if (browserContext) await browserContext.close();
    if (browser) await browser.close();
    if (server) server.kill('SIGTERM');
    fs.rmSync(temp, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
