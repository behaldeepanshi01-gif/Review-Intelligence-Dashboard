// Real Streamlit/WebSocket regression. Only code is copied into a temporary
// app: no workspace accounts, uploads, corrections or action histories are read.
// Run from the workspace: node review_intel_app/test_account_switch_browser.cjs
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const { spawn, spawnSync } = require('node:child_process');

const repo = path.resolve(__dirname, '..');
const password = 'synthetic-account-switch-only';
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
  // Kill the entire uv -> Python process group, then await exit before cleanup.
  const exited = new Promise(resolve => server.once('exit', resolve));
  const kill = signal => {
    try { process.kill(-server.pid, signal); } catch (e) {
      if (e.code !== 'ESRCH') throw e;
    }
  };
  kill('SIGTERM');
  const timeout = setTimeout(() => kill('SIGKILL'), 5000);
  try { await exited; } finally { clearTimeout(timeout); }
}

async function run() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'review-account-switch-'));
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
    console.error('Synthetic browser regression interrupted; removing temporary resources.');
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
    fs.mkdirSync(path.join(root, 'data'));
    const fixture = JSON.parse(python(`
import csv, json
from pathlib import Path
import dataset_store as D
import manager_identity as I
root = Path.cwd()
assert I.DB_PATH.resolve().is_relative_to(root)
def content(marker):
    import io
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["location", "date", "rating", "text", "reviewer", "review_id"])
    for index in range(2):
        writer.writerow([marker + " Restaurant", f"2026-10-0{index + 1}", 1,
                         marker + " food was cold and service was very slow.",
                         marker + " Guest", f"overlapping-review-{index}"])
    return out.getvalue().encode()
(root / "data/sample_reviews.csv").write_bytes(content("UNASSIGNED"))
store = D.DatasetStore(root / "data/uploads", root / "data/sample_reviews.csv")
fixtures, actions = {}, []
for account, marker in [("manager-a", "PRIVATE_ALPHA"), ("manager-b", "PRIVATE_BRAVO")]:
    dataset = store.save_snapshot(marker + "_dataset.csv", content(marker))
    I.set_account(account, ${JSON.stringify(password)},
                  {dataset["dataset_id"]: [marker + " Restaurant"]})
    fixtures[account] = dataset["dataset_id"]
    actions.append(dict(dataset_tag=dataset["dataset_id"],
                        action_id="overlapping-action-id", location=marker + " Restaurant",
                        theme="Service speed", status="Planned", start_date="2026-10-01",
                        due_date="2026-10-03", action_text=marker + " saved action",
                        owner=marker + " owner", created_on="2026-10-01T00:00:00+00:00"))
(root / "data/action_log.json").write_text(json.dumps(actions))
print(json.dumps(fixtures))
`));
    assert.notEqual(fixture['manager-a'], fixture['manager-b']);
    const actionPath = path.join(root, 'data/action_log.json');
    const originalActions = fs.readFileSync(actionPath);
    const port = await freePort();
    server = spawn('uv', ['run', '--project', repo, 'python', '-m', 'streamlit',
      'run', path.join(root, 'app.py'), '--server.port', String(port),
      '--server.address', '127.0.0.1', '--server.baseUrlPath', 'dashboard',
      '--server.headless', 'true', '--browser.gatherUsageStats', 'false'], {
      cwd: root, env, detached: true, stdio: ['ignore', 'pipe', 'pipe'],
    });
    server.stdout.on('data', data => { logs += data; });
    server.stderr.on('data', data => { logs += data; });
    let healthy = false;
    for (let i = 0; i < 60; i++) {
      try {
        healthy = (await fetch(`http://127.0.0.1:${port}/dashboard/_stcore/health`)).ok;
      } catch {}
      if (healthy) break;
      if (server.exitCode !== null) break;
      await delay(500);
    }
    assert(healthy, `Temporary dashboard did not start:\n${logs}`);
    browser = await chromium.launch({
      headless: true, executablePath: process.env.CHROMIUM_PATH || undefined,
      args: ['--no-sandbox'],
    });
    const context = await browser.newContext({ acceptDownloads: true,
      viewport: { width: 1440, height: 1100 } });
    page = await context.newPage();
    page.setDefaultTimeout(30000);
    await page.goto(`http://127.0.0.1:${port}/dashboard/`);

    async function login(username) {
      await page.getByLabel('Manager ID', { exact: true }).fill(username);
      await page.getByLabel('Manager report password', { exact: true }).fill(password);
      await page.getByRole('button', { name: 'Unlock restaurant dashboard', exact: true }).click();
      await page.getByRole('tab', { name: /Reply inbox/ }).waitFor();
      await page.getByText(`Signed in as ${username}`, { exact: true }).first().waitFor();
    }
    async function tab(name) {
      await page.getByRole('tab', { name: new RegExp(name) }).click();
    }
    async function noPrivate(markers) {
      // textContent includes inactive tabs; input values do not appear in text.
      const content = await page.locator('body').textContent();
      const values = await page.locator('input, textarea').evaluateAll(
        nodes => nodes.map(node => node.value).join('\\n'));
      for (const marker of markers) {
        assert(!content.includes(marker), `Private DOM text leaked: ${marker}`);
        assert(!values.includes(marker), `Private widget value leaked: ${marker}`);
      }
      assert.equal(await page.locator('[data-testid="stException"]').count(), 0);
    }
    async function exportRows(marker, approved) {
      await tab('Export');
      const event = page.waitForEvent('download');
      await page.getByRole('button', { name: 'Download analyzed reviews (CSV)', exact: true }).click();
      const download = await event;
      const file = path.join(root, `${marker}.csv`);
      await download.saveAs(file);
      const rows = JSON.parse(python(`
import csv, json
with open(${JSON.stringify(file)}) as stream:
    print(json.dumps(list(csv.DictReader(stream))))
`));
      assert.equal(rows.length, 2);
      assert.deepEqual(rows.map(row => row.review_id).sort(),
        ['overlapping-review-0', 'overlapping-review-1']);
      assert(rows.every(row => row.location === `${marker} Restaurant`));
      assert.equal(rows.filter(row => row.approved_reply).length, approved ? 1 : 0);
      if (approved) assert(rows.some(row => row.approved_reply === 'ALPHA_APPROVED_WORDING'));
      else assert(!JSON.stringify(rows).includes('ALPHA'));
    }
    async function actionDraft(marker) {
      await tab('Action tracker');
      await page.getByText(`Edit ${marker} Restaurant: Service speed · ${marker} owner`,
        { exact: true }).click();
      const editor = page.getByLabel('Manager action', { exact: true });
      assert.equal(await editor.inputValue(), `${marker} saved action`);
      await editor.fill(`${marker} UNSAVED_ACTION`);
      await editor.press('Tab');
      await page.getByLabel('Owner (optional)', { exact: true }).fill(`${marker} UNSAVED_OWNER`);
      await page.getByLabel('Owner (optional)', { exact: true }).press('Tab');
      // The production widget retention path must actually have run.
      await tab('Reply inbox');
      await tab('Action tracker');
      assert.equal(await editor.inputValue(), `${marker} UNSAVED_ACTION`);
    }

    await login('manager-a');
    await tab('Reply inbox');
    await page.getByLabel('Reply draft', { exact: true }).first().fill('ALPHA_APPROVED_WORDING');
    await page.getByRole('button', { name: 'Approve reply', exact: true }).first().click();
    await page.getByText('1 reviews in queue · 1 approved', { exact: true }).waitFor();
    await page.getByLabel('Reply draft', { exact: true }).fill('ALPHA_UNSAVED_REPLY');
    await page.getByLabel('Reply draft', { exact: true }).press('Tab');
    await actionDraft('PRIVATE_ALPHA');
    await exportRows('PRIVATE_ALPHA', true);
    await page.getByRole('button', { name: 'Lock restaurant dashboard', exact: true }).click();
    await page.getByLabel('Manager ID', { exact: true }).waitFor();
    await noPrivate(['PRIVATE_ALPHA', 'ALPHA_APPROVED_WORDING', 'ALPHA_UNSAVED_REPLY']);
    assert.equal(await page.getByRole('tab').count(), 0);

    // Deliberately reuse the same page, browser context and Streamlit session.
    await login('manager-b');
    await noPrivate(['PRIVATE_ALPHA', 'ALPHA_APPROVED_WORDING', 'ALPHA_UNSAVED_REPLY',
      fixture['manager-a']]);
    await page.getByRole('combobox', { name: 'Dataset', exact: true }).click();
    await noPrivate(['PRIVATE_ALPHA', fixture['manager-a']]);
    await page.keyboard.press('Escape');
    await tab('Reply inbox');
    await page.getByText('2 reviews in queue · 0 approved', { exact: true }).waitFor();
    assert.equal(await page.getByLabel('Reply draft', { exact: true }).count(), 2);
    await exportRows('PRIVATE_BRAVO', false);
    await actionDraft('PRIVATE_BRAVO');
    await noPrivate(['PRIVATE_ALPHA', 'ALPHA_APPROVED_WORDING', 'ALPHA_UNSAVED_REPLY']);
    assert.deepEqual(fs.readFileSync(actionPath), originalActions);
    console.log('PASS: A drafts/approval/export -> lock -> B; overlapping IDs stayed isolated.');

    // No click, reload or other browser input after changing grants. Real
    // 30-second fragments must evict the ENTIRE page, not just their own output.
    python(`import manager_identity as I
I.set_account("manager-b", ${JSON.stringify(password)}, {})`);
    await page.getByLabel('Manager ID', { exact: true }).waitFor({ timeout: 65000 });
    await noPrivate(['PRIVATE_ALPHA', 'PRIVATE_BRAVO', 'ALPHA_APPROVED_WORDING',
      'ALPHA_UNSAVED_REPLY', fixture['manager-a'], fixture['manager-b']]);
    assert.equal(await page.getByRole('tab').count(), 0);
    assert.equal(await page.getByLabel('Manager action', { exact: true }).count(), 0);
    assert.equal(await page.getByRole('button', { name: /Download analyzed reviews/ }).count(), 0);
    // Fresh B login has no grants and must not resurrect retained state.
    await page.getByLabel('Manager ID', { exact: true }).fill('manager-b');
    await page.getByLabel('Manager report password', { exact: true }).fill(password);
    await page.getByRole('button', { name: 'Unlock restaurant dashboard', exact: true }).click();
    await page.getByText('No datasets are assigned to this account.', { exact: false }).waitFor();
    await noPrivate(['PRIVATE_ALPHA', 'PRIVATE_BRAVO', 'ALPHA_APPROVED_WORDING']);
    assert.deepEqual(fs.readFileSync(actionPath), originalActions);
    console.log('PASS: live grant revocation removed old editors, reviews, dataset names and exports.');
  } catch (error) {
    if (page) console.error((await page.locator('body').innerText().catch(() => '')).slice(-10000));
    console.error(logs.slice(-6000));
    throw error;
  } finally {
    clearTimeout(deadline);
    await cleanup();
    process.removeListener('SIGINT', onInterrupt);
    process.removeListener('SIGTERM', onTerminate);
  }
}

run().catch(error => { console.error(error); process.exitCode = 1; });
