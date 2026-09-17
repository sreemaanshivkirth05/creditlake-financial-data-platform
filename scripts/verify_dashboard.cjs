/* Optional visual/interaction QA: npm install --no-save playwright;
   npx playwright install chromium; node scripts/verify_dashboard.cjs.
   CREDITLAKE_BROWSER can select an existing Chromium executable.
   CREDITLAKE_PLAYWRIGHT can select an existing Playwright module.
*/
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.CREDITLAKE_PLAYWRIGHT || 'playwright');

(async () => {
  const root=path.resolve(__dirname,'..');
  const browser=await chromium.launch({headless:true,
    executablePath:process.env.CREDITLAKE_BROWSER || undefined,
    args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1365,height:1150}});
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const targets=[{name:'standalone',url:pathToFileURL(path.join(root,'demo','CreditLake_Demo.html')).href}];
  if(process.env.CREDITLAKE_API_URL)targets.push({name:'api',url:process.env.CREDITLAKE_API_URL});
  const checks=[];
  try {
    for(const target of targets){
      await page.goto(target.url);
      await page.waitForFunction(()=>document.getElementById('revenue').textContent!=='—');
      assert.equal(await page.locator('#company option').count(),8);
      assert.ok((await page.locator('#company-name').textContent()).includes('TEXAS INSTRUMENTS'));
      assert.equal(await page.locator('#error').isVisible(),false);
      assert.ok(await page.locator('#evidence tr').count()>=8);
      const latest=await page.locator('#period-label').textContent();
      await page.locator('#cutoff').fill('2020-01-01');
      await page.locator('#filters button').click();
      await page.waitForFunction(()=>!document.getElementById('content').classList.contains('loading'));
      const old=await page.locator('#period-label').textContent();
      assert.notEqual(old,latest);
      assert.ok(old.includes('2018-12-31'));
      assert.ok(await page.locator('#chart circle').count()>0);
      await page.locator('#cutoff').fill('2000-01-01');
      await page.locator('#filters button').click();
      await page.waitForFunction(()=>!document.getElementById('content').classList.contains('loading'));
      assert.equal(await page.locator('#revenue').textContent(),'—');
      assert.ok((await page.locator('#evidence').textContent()).includes('No annual evidence'));
      await page.locator('#cutoff').fill('2026-09-17');
      await page.locator('#company').selectOption('WING');
      await page.waitForFunction(()=>document.getElementById('company-name').textContent.includes('WINGSTOP'));
      assert.equal(await page.locator('#error').isVisible(),false);
      await page.locator('#chart-metric').selectOption('net_income');
      assert.ok(await page.locator('#chart circle').count()>0);
      await page.locator('#company').selectOption('TXN');
      await page.waitForFunction(()=>document.getElementById('company-name').textContent.includes('TEXAS INSTRUMENTS'));
      await page.locator('#chart-metric').selectOption('revenue');
      await page.evaluate(()=>document.activeElement.blur());
      await page.screenshot({path:path.join(root,'demo',`dashboard-${target.name}.png`),fullPage:true});
      await page.setViewportSize({width:390,height:844});
      assert.ok(await page.locator('#company').isVisible());
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
      await page.screenshot({path:path.join(root,'demo',`dashboard-${target.name}-mobile.png`),fullPage:true});
      await page.setViewportSize({width:1365,height:1150});
      checks.push({target:target.name,issuer_count:8,historical_cutoff:true,empty_history:true,
        issuer_switch:true,chart_switch:true,mobile_no_overflow:true});
    }
    assert.deepEqual(errors,[]);
    const report={checks,javascript_errors:errors,browser:await browser.version()};
    fs.writeFileSync(path.join(root,'docs','evidence','dashboard-validation.json'),JSON.stringify(report,null,2)+'\n');
    process.stdout.write(JSON.stringify(report,null,2)+'\n');
  } finally {await browser.close()}
})().catch(error=>{process.stderr.write(String(error.stack)+'\n');process.exit(1)});
