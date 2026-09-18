/* Project end-to-end checks, executed in CI or an optional local test run.
   npm install --no-save playwright@1.58.2
   npx playwright install --with-deps chromium
   python scripts/verify_ui.py
*/
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { chromium } = require(process.env.CREDITLAKE_PLAYWRIGHT || "playwright");

(async () => {
  const root = path.resolve(__dirname, "..");
  const output = path.join(root, "validation", "dashboard");
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CREDITLAKE_BROWSER || undefined,
  });
  const page = await browser.newPage({
    viewport: { width: 1365, height: 1150 },
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const targets = [
    {
      name: "standalone",
      url: pathToFileURL(path.join(root, "demo", "CreditLake_Demo.html")).href,
    },
  ];
  if (process.env.CREDITLAKE_API_URL)
    targets.push({ name: "api", url: process.env.CREDITLAKE_API_URL });
  const checks = [];
  const loaded = () =>
    page.waitForFunction(
      () =>
        document.getElementById("content").getAttribute("aria-busy") ===
        "false",
    );
  const navigate = async (view) => {
    await page.locator('[data-view="' + view + '"]').click();
    await page.locator("#" + view).waitFor({ state: "visible" });
  };
  const apply = async (ticker, cutoff) => {
    await page.locator("#company").selectOption(ticker);
    await page.locator("#cutoff").fill(cutoff);
    await page.getByRole("button", { name: "Apply", exact: true }).click();
    await loaded();
    assert.equal(await page.locator("#error").isVisible(), false);
  };
  try {
    for (const target of targets) {
      await page.goto(target.url);
      await loaded();
      assert.equal(await page.locator("#company option").count(), 8);
      assert.equal(
        await page.locator("#company-name").textContent(),
        "Texas Instruments",
      );
      assert.equal(await page.locator("#error").isVisible(), false);
      assert.ok((await page.locator("#chart circle").count()) > 0);
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
      );

      // A fiscal-period change must update summaries and the exact source record.
      await page.locator("#period").selectOption("2023-12-31");
      assert.equal(await page.locator("#revenue").textContent(), "$17.52B");
      await navigate("sources");
      await page
        .getByRole("button", { name: "View source for Revenue", exact: true })
        .click();
      assert.equal(
        await page.locator("#source-value").textContent(),
        "$17,519,000,000",
      );
      assert.ok(
        (await page.locator("#source-period").textContent()).includes(
          "31 Dec 2023",
        ),
      );
      assert.match(
        await page.locator("#source-fields").textContent(),
        /[a-f0-9]{64}/,
      );
      if (target.name === "api") {
        await page
          .getByRole("link", {
            name: "Download original source (.json.gz)",
            exact: true,
          })
          .waitFor();
        assert.ok(
          (await page.locator("#source-fields").textContent()).includes(
            "raw.facts",
          ),
        );
      }
      await page.keyboard.press("Escape");
      assert.equal(await page.locator("#source-dialog").isVisible(), false);

      await navigate("overview");
      await apply("TXN", "2020-01-01");
      assert.equal(await page.locator("#period").inputValue(), "2018-12-31");
      assert.ok((await page.locator("#chart circle").count()) > 0);
      // The export must contain this filtered history, not the published latest mart.
      const downloadPromise = page.waitForEvent("download");
      await page
        .getByRole("button", { name: "Export CSV", exact: true })
        .click();
      const download = await downloadPromise;
      assert.equal(
        download.suggestedFilename(),
        "creditlake-TXN-as-of-2020-01-01.csv",
      );
      const csv = fs.readFileSync(await download.path(), "utf8");
      const lines = csv.trim().split(/\r?\n/);
      assert.ok(lines[0].startsWith("ticker,as_of,period_end,revenue"));
      assert.equal(
        lines.length - 1,
        await page.locator("#annual-statements tbody tr").count(),
      );
      assert.ok(
        lines
          .slice(1)
          .every((line) => line.startsWith('"TXN","2020-01-01","201')),
      );
      assert.ok(lines.some((line) => line.includes('"2018-12-31"')));
      assert.ok(!csv.includes('"2023-12-31"'));

      await apply("TXN", "2000-01-01");
      assert.equal(await page.locator("#revenue").textContent(), "—");
      assert.equal(await page.locator("#export-button").isDisabled(), true);
      await navigate("sources");
      assert.ok(
        (await page.locator("#evidence").textContent()).includes(
          "No source facts",
        ),
      );
      await navigate("overview");
      await apply("WING", "2026-09-17");
      assert.equal(
        await page.locator("#company-name").textContent(),
        "Wingstop",
      );
      await page.locator("#chart-metric").selectOption("net_income");
      assert.ok((await page.locator("#chart circle").count()) > 0);
      await navigate("changes");
      assert.ok(
        (await page.locator("#revision-count").textContent()).includes(
          "changes",
        ),
      );

      await navigate("quality");
      assert.equal(await page.locator("#filters").isVisible(), false);
      assert.equal(await page.locator("#periods-count").textContent(), "89");
      assert.equal(await page.locator("#complete-count").textContent(), "35");
      assert.equal(await page.locator("#incomplete-count").textContent(), "54");
      assert.equal(await page.locator("#balance-count").textContent(), "5");
      assert.equal(
        await page.locator("#checks").textContent(),
        "23 checks passed",
      );
      assert.equal(await page.locator("#quality-issuers tr").count(), 8);
      assert.equal(await page.locator("#quality-balances tr").count(), 5);
      await page
        .getByRole("button", { name: /^View .+ period / })
        .first()
        .click();
      await loaded();
      assert.equal(await page.locator("#sources").isVisible(), true);
      assert.ok((await page.locator("#evidence button").count()) > 0);

      // API failures must clear old company values and expose a working retry.
      if (target.name === "api") {
        await page.route("**/api/companies/WING/history*", (route) =>
          route.fulfill({ status: 503, body: "unavailable" }),
        );
        await page.locator("#company").selectOption("WING");
        await page.getByRole("button", { name: "Apply", exact: true }).click();
        await loaded();
        assert.equal(await page.locator("#error").isVisible(), true);
        assert.equal(await page.locator("#revenue").textContent(), "—");
        assert.equal(await page.locator("#export-button").isDisabled(), true);
        await page.unroute("**/api/companies/WING/history*");
        await page.getByRole("button", { name: "Retry", exact: true }).click();
        await loaded();
        assert.equal(await page.locator("#error").isVisible(), false);
        assert.equal(
          await page.locator("#company-name").textContent(),
          "Wingstop",
        );
      }
      await navigate("overview");
      await apply("TXN", "2026-09-17");
      await page.locator("#chart-metric").selectOption("revenue");
      await page.screenshot({
        path: path.join(output, "dashboard-" + target.name + "-desktop.jpg"),
        fullPage: true,
        type: "jpeg",
        quality: 92,
      });

      await page.setViewportSize({ width: 390, height: 844 });
      for (const view of ["sources", "changes", "quality", "overview"]) {
        await navigate(view);
        assert.equal(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
          true,
          view + " mobile overflow",
        );
      }
      assert.equal(await page.locator("#company").isVisible(), true);
      assert.ok((await page.locator("#chart circle").count()) > 0);
      await page.screenshot({
        path: path.join(output, "dashboard-" + target.name + "-mobile.jpg"),
        fullPage: true,
        type: "jpeg",
        quality: 92,
      });
      await page.setViewportSize({ width: 1365, height: 1150 });
      checks.push({
        target: target.name,
        issuer_count: 8,
        period_summary_and_source: true,
        source_details_and_escape: true,
        historical_cutoff: true,
        filtered_csv_export: true,
        empty_history: true,
        issuer_switch: true,
        chart_switch: true,
        quality_totals_and_drilldown: true,
        api_error_and_retry: target.name === "api" ? true : null,
        desktop_no_overflow: true,
        mobile_all_views_no_overflow: true,
      });
    }
    assert.deepEqual(errors, []);
    const report = {
      status: "pass",
      viewports: [
        { width: 1365, height: 1150 },
        { width: 390, height: 844 },
      ],
      checks,
      javascript_errors: errors,
      browser: await browser.version(),
    };
    fs.writeFileSync(
      path.join(output, "dashboard-validation.json"),
      JSON.stringify(report, null, 2) + "\n",
    );
    process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  } catch (error) {
    await page.screenshot({
      path: path.join(output, "failure.jpg"),
      fullPage: true,
      type: "jpeg",
    });
    throw error;
  } finally {
    await browser.close();
  }
})().catch((error) => {
  process.stderr.write(String(error.stack) + "\n");
  process.exit(1);
});
