// Isolated real-browser regression for manager warning, save and expiry.
// All app code/data/accounts live in a temporary directory; only synthetic
// sample data and a synthetic manager are used. Run with:
// node review_intel_app/test_session_expiry_browser.cjs
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const { spawn, spawnSync } = require('node:child_process');

const repo = path.resolve(__dirname, '..');
const username = 'session-expiry-synthetic-manager';
const password = 'synthetic-session-expiry-password';
const dataset = 'builtin:synthetic-sample';
const location = 'Cafe North';
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function freePort() {
  const socket = net.createServer();
  await new Promise((resolve, reject) => {
    socket.once('error', reject);
    socket.listen(0, '127.0.0.1', resolve);
  });
  const port = socket.address().port;
  await new Promise(resolve => socket.close(resolve));
  return port;
}

async function stop(server) {
  if (!server || server.exitCode !== null) return;
  const exited = new Promise(resolve => server.once('exit', resolve));
  try { process.kill(-server.pid, 'SIGTERM'); } catch (error) {
    if (error.code !== 'ESRCH') throw error;
  }
  const timer = setTimeout(() => {
    try { process.kill(-server.pid, 'SIGKILL'); } catch {}
  }, 5000);
  try { await exited; } finally { clearTimeout(timer); }
}

async function main() {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'review-session-expiry-'));
  const screenshots = path.join(os.tmpdir(), 'review-session-expiry');
  let server, browser, logs = '';
  const env = { ...process.env, PYTHONPATH: temp };
  const py = script => {
    const result = spawnSync('uv', ['run', '--project', repo, 'python', '-c', script], {
      cwd: temp, env, encoding: 'utf8', timeout: 30000,
    });
    assert.equal(result.status, 0, result.stderr || result.error?.message);
    return result.stdout.trim();
  };
  try {
    fs.mkdirSync(path.join(temp, 'data'), { recursive: true });
    for (const file of fs.readdirSync(__dirname).filter(name => name.endsWith('.py'))) {
      fs.copyFileSync(path.join(__dirname, file), path.join(temp, file));
    }
    fs.copyFileSync(path.join(__dirname, 'data/sample_reviews.csv'),
      path.join(temp, 'data/sample_reviews.csv'));
    fs.mkdirSync(path.join(temp, 'data/uploads'), { recursive: true });
    const rows = fs.readFileSync(path.join(temp, 'data/sample_reviews.csv'), 'utf8')
      .split(/\r?\n/);
    const sampleLocation = rows[1].split(',')[1].replace(/^"|"$/g, '');
    // Grant only the built-in synthetic sample's actual location.
    const allowedLocation = sampleLocation || location;
    const actionLocation = allowedLocation;
    const actionPath = path.join(temp, 'data/action_log.json');
    fs.writeFileSync(actionPath, JSON.stringify([{
      dataset_tag: dataset, action_id: 'expiry-synthetic-action',
      location: actionLocation, theme: 'Service speed', status: 'Planned',
      start_date: '2025-12-29', due_date: '2026-12-31',
      action_text: 'Synthetic baseline action', owner: 'Synthetic baseline owner',
      created_on: '2026-01-01T00:00:00+00:00',
    }], null, 2));
    const clock = path.join(temp, 'clock');
    const initial = Math.floor(Date.now() / 1000) + 60;
    fs.writeFileSync(clock, String(initial));
    py(`
import manager_identity as I
I.set_account(${JSON.stringify(username)}, ${JSON.stringify(password)},
              {${JSON.stringify(dataset)}: [${JSON.stringify(actionLocation)}]})
`);
    fs.writeFileSync(path.join(temp, 'harness.py'), `
import runpy
from pathlib import Path
import manager_identity as identity
import manager_report_access as access
ROOT = Path(__file__).parent
class ControlledClock:
    def time(self):
        return float((ROOT / "clock").read_text())
# Patch only each imported module's local clock binding, never global time.time.
identity.time = ControlledClock()
access.time = ControlledClock()
runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
`);
    const port = await freePort();
    server = spawn('uv', ['run', '--project', repo, 'python', '-m', 'streamlit', 'run',
      path.join(temp, 'harness.py'), '--server.port', String(port),
      '--server.address', '127.0.0.1', '--server.baseUrlPath', 'dashboard',
      '--server.headless', 'true', '--browser.gatherUsageStats', 'false'], {
      cwd: temp, env, detached: true, stdio: ['ignore', 'pipe', 'pipe'],
    });
    server.stdout.on('data', data => { logs += data; });
    server.stderr.on('data', data => { logs += data; });
    let healthy = false;
    for (let i = 0; i < 60; i++) {
      try { healthy = (await fetch(`http://127.0.0.1:${port}/dashboard/_stcore/health`)).ok; }
      catch {}
      if (healthy || server.exitCode !== null) break;
      await delay(500);
    }
    assert(healthy, `Temporary dashboard failed to start:\n${logs}`);
    browser = await chromium.launch({
      executablePath: process.env.CHROMIUM_PATH || undefined,
      headless: true, args: ['--no-sandbox'],
    });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    const page = await context.newPage();
    page.setDefaultTimeout(30000);
    await page.goto(`http://127.0.0.1:${port}/dashboard/`);
    await page.getByLabel('Manager ID', { exact: true }).fill(username);
    await page.getByLabel('Manager report password', { exact: true }).fill(password);
    await page.getByRole('button', { name: 'Unlock restaurant dashboard', exact: true }).click();
    await page.getByRole('tab', { name: /Action tracker/i }).waitFor();
    await page.getByRole('tab', { name: /Action tracker/i }).click();
    await page.getByText(
      new RegExp(`Edit ${actionLocation}: Service speed · Synthetic baseline owner`)
    ).click();
    const editor = page.getByLabel('Manager action', { exact: true });
    await editor.waitFor({ state: 'visible' });

    // At 301 seconds remaining, no warning should be rendered.
    fs.writeFileSync(clock, String(initial + 1800 - 301));
    await page.waitForTimeout(11000);
    assert.doesNotMatch(await page.locator('body').innerText(), /Sign-in expires in/);

    // Keep a browser-only, focused text edit while the 10-second fragment timer
    // displays the warning. No browser input occurs during the clock advance.
    await editor.fill('Authorized warning-time saved draft');
    assert.equal(await editor.evaluate(el => document.activeElement === el), true);
    fs.writeFileSync(clock, String(initial + 1800 - 300));
    await page.getByText(/Sign-in expires in 5 minutes or less/).waitFor({
      state: 'visible', timeout: 25000,
    });
    assert.equal(await editor.inputValue(), 'Authorized warning-time saved draft');
    assert.equal(await editor.evaluate(el => document.activeElement === el), true,
      'unblurred editor lost focus during warning fragment rerun');
    await page.screenshot({ path: `${screenshots}-warning.png`, fullPage: true });

    // Save explicitly while still authorized; confirm persistence and no renewal
    // by later checking that the original exact expiry still gates the session.
    await page.getByRole('button', { name: 'Save updates', exact: true }).click();
    await page.getByText('Action updated.').waitFor({ state: 'visible', timeout: 10000 })
      .catch(() => {}); // Streamlit toast can disappear before Playwright observes it.
    const saved = JSON.parse(fs.readFileSync(actionPath, 'utf8'));
    assert.equal(saved[0].action_text, 'Authorized warning-time saved draft');
    assert.equal(saved[0].owner, 'Synthetic baseline owner');
    // Wait for Streamlit's post-save rerun to rebuild the keyed editor before
    // entering the second draft (the log write can precede the rerun).
    await page.waitForFunction(
      expected => [...document.querySelectorAll('textarea')]
        .some(node => node.value === expected),
      'Authorized warning-time saved draft', { timeout: 15000 });

    // Retain a second unsaved draft in server widget state, then advance the
    // clock to the exact expiry without any subsequent browser interaction.
    await editor.fill('PRIVATE_UNSAVED_DRAFT_AT_EXPIRY');
    await editor.press('Tab');
    assert.equal(await editor.inputValue(), 'PRIVATE_UNSAVED_DRAFT_AT_EXPIRY');
    fs.writeFileSync(clock, String(initial + 1800));
    await page.getByLabel('Manager ID', { exact: true }).waitFor({
      state: 'visible', timeout: 25000,
    });
    const gatedText = await page.locator('body').innerText();
    assert.match(gatedText, /Sign in with your individual manager account/);
    assert.doesNotMatch(gatedText, /PRIVATE_UNSAVED_DRAFT_AT_EXPIRY|Action tracker/);
    assert.equal(await page.getByRole('tab').count(), 0);
    assert.equal(await page.getByLabel('Manager action', { exact: true }).count(), 0);
    await page.screenshot({ path: `${screenshots}-expired.png`, fullPage: true });

    // Re-login on the same browser page: only the explicitly saved baseline may
    // return; the expired session's private draft must not be exposed.
    await page.getByLabel('Manager ID', { exact: true }).fill(username);
    await page.getByLabel('Manager report password', { exact: true }).fill(password);
    await page.getByRole('button', { name: 'Unlock restaurant dashboard', exact: true }).click();
    await page.getByRole('tab', { name: /Action tracker/i }).waitFor();
    await page.getByRole('tab', { name: /Action tracker/i }).click();
    await page.getByText(
      new RegExp(`Edit ${actionLocation}: Service speed · Synthetic baseline owner`)
    ).click();
    const newEditor = page.getByLabel('Manager action', { exact: true });
    assert.equal(await newEditor.inputValue(), 'Authorized warning-time saved draft');
    assert.doesNotMatch(await page.locator('body').innerText(),
      /PRIVATE_UNSAVED_DRAFT_AT_EXPIRY/);
    assert.deepEqual(JSON.parse(fs.readFileSync(actionPath, 'utf8'))[0].action_text,
      'Authorized warning-time saved draft');
    await page.screenshot({ path: `${screenshots}-relogin.png`, fullPage: true });
    console.log(`PASS: warning absent at 301s; warning appeared at 300s without browser `
      + `input; focused unblurred draft survived; explicit save persisted without renewal; `
      + `exact expiry removed private UI and discarded a second unsaved draft. `
      + `Evidence: ${screenshots}-warning.png, ${screenshots}-expired.png, `
      + `${screenshots}-relogin.png`);
  } catch (error) {
    console.error(logs.slice(-6000));
    if (browser) {
      const pages = browser.contexts().flatMap(context => context.pages());
      if (pages[0]) {
        console.error('Page text:', (await pages[0].locator('body').innerText().catch(() => '')).slice(-6000));
        await pages[0].screenshot({ path: `${screenshots}-failure.png`, fullPage: true }).catch(() => {});
      }
    }
    throw error;
  } finally {
    if (browser) await browser.close();
    await stop(server);
    fs.rmSync(temp, { recursive: true, force: true });
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
