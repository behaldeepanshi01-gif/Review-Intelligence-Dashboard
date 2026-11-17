// Isolated real-browser regression for individual action-draft discard.
// Only Python code is copied to a temporary app; all accounts, reviews and
// action history are synthetic. Screenshots are retained outside that copy.
// Run: node review_intel_app/test_action_discard_browser.cjs
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const { spawn, spawnSync } = require('node:child_process');

const repo = path.resolve(__dirname, '..');
const password = 'synthetic-action-discard-password';
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
  const kill = signal => {
    try { process.kill(-server.pid, signal); } catch (error) {
      if (error.code !== 'ESRCH') throw error;
    }
  };
  kill('SIGTERM');
  const timeout = setTimeout(() => kill('SIGKILL'), 5000);
  try { await exited; } finally { clearTimeout(timeout); }
}

async function run() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'review-action-discard-'));
  const evidence = path.join(os.tmpdir(), `review-action-discard-evidence-${Date.now()}`);
  fs.mkdirSync(evidence, { recursive: true });
  let server, browser, page, logs = '';
  const env = { ...process.env, PYTHONPATH: root };
  const python = script => {
    const result = spawnSync('uv', ['run', '--project', repo, 'python', '-c', script], {
      cwd: root, env, encoding: 'utf8', timeout: 30000,
    });
    assert.equal(result.status, 0, result.stderr || result.error?.message);
    return result.stdout.trim();
  };
  let cleanupPromise;
  const cleanup = () => cleanupPromise ||= (async () => {
    try { if (browser) await browser.close(); }
    finally {
      await stop(server);
      fs.rmSync(root, { recursive: true, force: true });
    }
  })();
  const interrupt = code => {
    console.error('Synthetic discard browser test interrupted; cleaning temporary resources.');
    cleanup().finally(() => process.exit(code));
  };
  const onInterrupt = () => interrupt(130);
  const onTerminate = () => interrupt(143);
  process.once('SIGINT', onInterrupt);
  process.once('SIGTERM', onTerminate);
  const deadline = setTimeout(() => interrupt(1), 180000);
  try {
    for (const name of fs.readdirSync(__dirname).filter(name => name.endsWith('.py'))) {
      fs.copyFileSync(path.join(__dirname, name), path.join(root, name));
    }
    fs.mkdirSync(path.join(root, 'data/uploads'), { recursive: true });
    const fixture = JSON.parse(python(`
import csv, json
from pathlib import Path
import action_tracker as A
import dataset_store as D
import manager_identity as I
root = Path.cwd()
assert I.DB_PATH.resolve().is_relative_to(root)
rows = [["Synthetic Cafe", f"2026-08-0{i+1}", 5,
         "The dish was delicious and fresh.", f"Baseline Guest {i}", f"base-{i}"]
        for i in range(5)]
rows += [["Synthetic Cafe", f"2026-11-0{i+1}", 1,
          "The dish was terrible and very disappointing.", f"Recent Guest {i}", f"recent-{i}"]
         for i in range(5)]
with (root / "data/sample_reviews.csv").open("w", newline="", encoding="utf-8") as stream:
    writer = csv.writer(stream)
    writer.writerow(["location", "date", "rating", "text", "reviewer", "review_id"])
    writer.writerows(rows)
content = (root / "data/sample_reviews.csv").read_bytes()
store = D.DatasetStore(root / "data/uploads", root / "data/sample_reviews.csv")
dataset = store.save_snapshot("synthetic-discard.csv", content)
I.set_account("synthetic-manager", ${JSON.stringify(password)},
              {dataset["dataset_id"]: ["Synthetic Cafe"]})
action = dict(dataset_tag=dataset["dataset_id"], action_id="synthetic-existing-action",
              location="Synthetic Cafe", theme="Service speed", status="Planned",
              start_date="2026-10-01", due_date="2026-10-03",
              action_text="Synthetic saved plan", owner="Synthetic saved owner",
              created_on="2026-10-01T00:00:00+00:00")
A.save_actions(root / "data/action_log.json", [action])
print(json.dumps({"dataset_id": dataset["dataset_id"], "action_id": action["action_id"]}))
`));
    const actionPath = path.join(root, 'data/action_log.json');
    const originalLog = fs.readFileSync(actionPath);
    const port = await freePort();
    server = spawn('uv', ['run', '--project', repo, 'python', '-m', 'streamlit',
      'run', path.join(root, 'app.py'), '--server.port', String(port),
      '--server.address', '127.0.0.1', '--server.headless', 'true',
      '--browser.gatherUsageStats', 'false'], {
      cwd: root, env, detached: true, stdio: ['ignore', 'pipe', 'pipe'],
    });
    server.stdout.on('data', data => { logs += data; });
    server.stderr.on('data', data => { logs += data; });
    let healthy = false;
    for (let i = 0; i < 60; i++) {
      try { healthy = (await fetch(`http://127.0.0.1:${port}/_stcore/health`)).ok; } catch {}
      if (healthy) break;
      if (server.exitCode !== null) break;
      await delay(500);
    }
    assert(healthy, `Temporary dashboard did not start:\n${logs}`);

    browser = await chromium.launch({
      headless: true,
      executablePath: process.env.CHROMIUM_PATH || undefined,
      args: ['--no-sandbox'],
    });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    page = await context.newPage();
    page.setDefaultTimeout(30000);
    await page.goto(`http://127.0.0.1:${port}/`);
    await page.getByLabel('Manager ID', { exact: true }).fill('synthetic-manager');
    await page.getByLabel('Manager report password', { exact: true }).fill(password);
    await page.getByRole('button', { name: 'Unlock restaurant dashboard', exact: true }).click();
    await page.getByText('Signed in as synthetic-manager', { exact: true }).waitFor();

    await page.getByRole('tab', { name: /Action tracker/ }).click();
    await page.getByText('Edit Synthetic Cafe: Service speed · Synthetic saved owner',
      { exact: true }).click();
    await page.waitForFunction(() =>
      document.querySelector('textarea[aria-label="Manager action"]')?.value === 'Synthetic saved plan');
    const existingText = page.getByLabel('Manager action', { exact: true });
    const existingOwner = page.getByLabel('Owner (optional)', { exact: true }).nth(1);
    const existingStatus = page.getByLabel('Status', { exact: true });
    assert.equal(await existingText.inputValue(), 'Synthetic saved plan');
    assert.equal(await existingOwner.inputValue(), 'Synthetic saved owner');

    await existingText.fill('Unsaved existing draft text');
    await existingOwner.fill('Unsaved existing draft owner');
    await page.getByRole('tab', { name: /Early warnings/ }).click();
    await page.getByText('Synthetic Cafe: Food & flavor', { exact: true }).waitFor();
    const newText = page.getByLabel('Action to try', { exact: true });
    const newOwner = page.getByLabel('Owner (optional)', { exact: true }).first();
    await newText.waitFor({ state: 'visible' });
    const newTextDefault = await newText.inputValue();
    const newOwnerDefault = await newOwner.inputValue();
    const newStart = page.locator('input[type="date"]').nth(0);
    const newDue = page.locator('input[type="date"]').nth(1);
    const newStartDefault = await newStart.inputValue();
    const newDueDefault = await newDue.inputValue();
    await newText.fill('Separate new-action draft');
    await newOwner.fill('Separate new-action owner');
    await page.screenshot({ path: path.join(evidence, '01-both-drafts.png'), fullPage: true });

    // Refocus an existing field immediately before clicking discard so the
    // button click itself must blur/synchronize the last typed value.
    await page.getByRole('tab', { name: /Action tracker/ }).click();
    await existingOwner.fill('Focused existing owner before discard');
    await page.getByRole('button', { name: 'Discard unsaved changes', exact: true }).click();
    await page.getByText("Discard this editor's unsaved changes?", { exact: false }).waitFor();
    assert.equal(await existingText.inputValue(), 'Unsaved existing draft text');
    assert.equal(await existingOwner.inputValue(), 'Focused existing owner before discard');
    assert.deepEqual(fs.readFileSync(actionPath), originalLog);
    await page.screenshot({ path: path.join(evidence, '02-existing-confirmation.png'), fullPage: true });
    await page.getByRole('button', { name: 'Keep editing', exact: true }).click();
    await page.getByRole('button', { name: 'Confirm discard', exact: true })
      .waitFor({ state: 'hidden' });
    assert.equal(await existingText.inputValue(), 'Unsaved existing draft text');
    assert.equal(await existingOwner.inputValue(), 'Focused existing owner before discard');
    await page.screenshot({ path: path.join(evidence, '03-keep-editing.png'), fullPage: true });

    // Reopen confirmation and discard the unchanged saved snapshot.
    await existingOwner.fill('Focused existing owner before confirm');
    await page.getByRole('button', { name: 'Discard unsaved changes', exact: true }).click();
    await page.getByRole('button', { name: 'Confirm discard', exact: true }).click();
    await page.waitForFunction(() =>
      document.querySelector('textarea[aria-label="Manager action"]')?.value === 'Synthetic saved plan');
    assert.equal(await existingOwner.inputValue(), 'Synthetic saved owner');
    assert.equal(await existingStatus.inputValue(), 'Planned');
    assert.deepEqual(fs.readFileSync(actionPath), originalLog,
      'same-snapshot discard must not write action history');
    await page.getByRole('tab', { name: /Early warnings/ }).click();
    assert.equal(await newText.inputValue(), 'Separate new-action draft');
    assert.equal(await newOwner.inputValue(), 'Separate new-action owner');
    await page.screenshot({ path: path.join(evidence, '04-existing-reset-new-draft-kept.png'),
      fullPage: true });

    // Also test blur/click synchronization and reset of the new-action form.
    await newText.fill('Focused new-action draft before discard');
    await newOwner.fill('Focused new-action owner before discard');
    await page.getByRole('button', { name: 'Discard new-action draft', exact: true }).click();
    await page.getByText("Discard this editor's unsaved changes?", { exact: false }).waitFor();
    assert.equal(await newText.inputValue(), 'Focused new-action draft before discard');
    assert.equal(await newOwner.inputValue(), 'Focused new-action owner before discard');
    await page.screenshot({ path: path.join(evidence, '05-new-confirmation.png'), fullPage: true });
    await page.getByRole('button', { name: 'Confirm discard', exact: true }).click();
    await page.waitForFunction(expected =>
      [...document.querySelectorAll('textarea')].some(el =>
        el.getAttribute('aria-label') === 'Action to try' && el.value === expected),
      newTextDefault);
    assert.equal(await newText.inputValue(), newTextDefault);
    assert.equal(await newOwner.inputValue(), newOwnerDefault);
    assert.equal(await newStart.inputValue(), newStartDefault);
    assert.equal(await newDue.inputValue(), newDueDefault);
    assert.deepEqual(fs.readFileSync(actionPath), originalLog,
      'new-action discard must not write action history');
    await page.screenshot({ path: path.join(evidence, '06-new-reset-no-save.png'), fullPage: true });

    // Simulate a concurrent saved-action change between request and confirm.
    await page.getByRole('tab', { name: /Action tracker/ }).click();
    await existingText.fill('Concurrent-check draft');
    await existingOwner.fill('Concurrent-check owner');
    await page.getByRole('button', { name: 'Discard unsaved changes', exact: true }).click();
    await page.getByText("Discard this editor's unsaved changes?", { exact: false }).waitFor();
    python(`
import action_tracker as A
from pathlib import Path
path = Path(${JSON.stringify(actionPath)})
rows = A.load_actions(path)
latest = [dict(row) for row in rows]
latest[0]["action_text"] = "Concurrent latest saved plan"
A.save_actions(path, latest, expected_actions=rows)
`);
    const concurrentLog = fs.readFileSync(actionPath);
    await page.getByRole('button', { name: 'Confirm discard', exact: true }).click();
    await page.getByText("Discard this editor's unsaved changes?", { exact: false }).waitFor();
    assert.equal(await existingText.inputValue(), 'Concurrent-check draft');
    assert.equal(await existingOwner.inputValue(), 'Concurrent-check owner');
    await page.waitForFunction(() => {
      const cells = [...document.querySelectorAll('[role="gridcell"]')]
        .map(cell => cell.textContent.trim());
      return cells.includes('Concurrent latest saved plan')
        && cells.includes('Concurrent-check draft');
    });
    await page.screenshot({ path: path.join(evidence, '07-concurrency-updated-comparison.png'),
      fullPage: true });
    await page.getByRole('button', { name: 'Confirm discard', exact: true }).click();
    await page.waitForFunction(() =>
      document.querySelector('textarea[aria-label="Manager action"]')?.value ===
      'Concurrent latest saved plan');
    assert.equal(await existingText.inputValue(), 'Concurrent latest saved plan');
    assert.deepEqual(fs.readFileSync(actionPath), concurrentLog,
      'concurrency-confirmed discard must not write action history');
    await page.screenshot({ path: path.join(evidence, '08-concurrency-reset-latest.png'),
      fullPage: true });

    console.log(JSON.stringify({
      result: 'PASS',
      fixture: { manager: 'synthetic-manager', dataset: fixture.dataset_id },
      verified: [
        'focused saved-action field synchronized by discard click',
        'Keep editing preserved values',
        'same-snapshot saved-action discard reset only its editor without changing action_log bytes',
        'separate new-action draft survived existing-action discard',
        'focused new-action draft discard restored all captured defaults without saving',
        'concurrent saved-action change refreshed comparison; first confirm preserved draft; second reset to latest',
      ],
      screenshots: evidence,
    }, null, 2));
  } catch (error) {
    if (page) {
      const body = await page.locator('body').innerText().catch(() => '');
      console.error('PAGE TAIL', body.slice(-5000));
      await page.screenshot({ path: path.join(evidence, 'failure.png'), fullPage: true })
        .catch(() => {});
    }
    console.error('SERVER LOG TAIL', logs.slice(-5000));
    console.error('EVIDENCE', evidence);
    throw error;
  } finally {
    clearTimeout(deadline);
    await cleanup();
    process.removeListener('SIGINT', onInterrupt);
    process.removeListener('SIGTERM', onTerminate);
  }
}

run().catch(error => { console.error(error); process.exitCode = 1; });
