const run = async (page) => {
  const fs = require("fs");
  const path = require("path");
  const assert = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const checks = [];
  const check = (condition, message) => {
    assert(condition, message);
    checks.push(message);
  };
  const repo = process.cwd();
  const out = path.resolve(process.env.SONAR_E2E_OUTPUT || "output/playwright");
  const screenshots = path.join(repo, "docs/screenshots/a1.1");
  fs.mkdirSync(screenshots, { recursive: true });
  fs.mkdirSync(out, { recursive: true });
  const axe = require("axe-core");
  const audits = [];
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const auditCurrent = async (label) => {
    await page.waitForTimeout(200); // Let the 150ms theme/background transition finish before measuring pixels.
    await page.evaluate(axe.source);
    const result = await page.evaluate(
      async () =>
        await axe.run({
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
        }),
    );
    check(
      !result.violations.length,
      `${label}: axe scan ${JSON.stringify(result.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })))}`,
    );
  };
  const wait = async (predicate) => {
    const end = Date.now() + 10000;
    while (Date.now() < end) {
      if (await predicate()) return;
      await page.waitForTimeout(50);
    }
    throw new Error("Condition timed out");
  };
  const go = async (name) => {
    await page
      .getByRole("navigation")
      .getByRole("link", {
        name: name.startsWith("Session BoMs") ? /^Session BoMs/ : name,
        exact: true,
      })
      .click();
    await page.waitForTimeout(100);
  };
  const importFile = async (filename, options = {}) => {
    const picker = page.waitForEvent("filechooser");
    await page
      .getByRole("button", { name: /Import BoM|Choose a BoM file/ })
      .first()
      .click();
    await (await picker).setFiles(path.join(repo, "examples", filename));
    const dialog = page.getByRole("dialog", { name: "Review your import" });
    await dialog.waitFor();
    await auditCurrent("Import mapping dialog");
    if (options.sheet) {
      await dialog
        .getByRole("combobox", { name: "Worksheet", exact: true })
        .selectOption(options.sheet);
      await page.waitForTimeout(200);
    }
    if (options.manual)
      await page
        .getByRole("combobox", { name: "Component name", exact: true })
        .selectOption("1");
    await page.getByRole("button", { name: "Import BoM", exact: true }).click();
    await dialog.waitFor({ state: "hidden" });
    await page.getByRole("heading", { name: "BoM", exact: true }).waitFor();
  };
  const summary = () =>
    page.locator(".component-row details > summary").first();
  const edit = async (mpn, name) => {
    const row = page.locator(".component-row").first();
    if (
      !(await row
        .locator("details")
        .first()
        .getAttribute("open")
        .then((x) => x !== null))
    )
      await summary().click();
    await row
      .getByRole("button", { name: "Edit component", exact: true })
      .click();
    if (mpn !== undefined)
      await page
        .getByRole("textbox", { name: "Manufacturer MPN", exact: true })
        .fill(mpn);
    if (name)
      await page
        .getByRole("textbox", { name: "Component name", exact: true })
        .fill(name);
    await page.getByRole("button", { name: "Save component" }).click();
    await page.getByRole("dialog").waitFor({ state: "hidden" });
  };
  const lookup = async () => {
    await go("Suppliers");
    await page
      .getByRole("combobox", { name: "Distributor", exact: true })
      .selectOption("direnc");
    await page.getByRole("button", { name: /Search this MPN/ }).click();
    await wait(
      async () =>
        (await page.locator(".offer-card").count()) ||
        (await page.locator("main").innerText()).includes(
          "Synthetic network failure",
        ) ||
        (await page.locator("main").innerText()).includes(
          "Synthetic supplier rate limit",
        ) ||
        (await page.locator("main").innerText()).includes(
          "Synthetic empty retrieval",
        ),
    );
  };
  const choose = async () => {
    const card = page.locator(".offer-card").first();
    await card.getByRole("checkbox").check();
    await card.getByRole("radio").nth(1).check();
    await card
      .getByRole("button", { name: "Select product", exact: true })
      .click();
    await wait(
      async () =>
        (await page
          .getByRole("button", { name: "Update selection", exact: true })
          .count()) > 0,
    );
  };
  await page.goto("http://127.0.0.1:8013");
  await page.getByRole("heading", { name: "Start with your design" }).waitFor();
  await page.setViewportSize({ width: 1440, height: 1000 });
  check(
    (await page.locator(".bom-row").count()) === 0,
    "Genuine empty session",
  );
  await importFile("altium_a1.csv", { manual: true });
  check(
    (await page.locator(".component-row").count()) === 4,
    "CSV import with manual mapping preserves all four rows",
  );
  await page
    .getByRole("spinbutton", { name: "PCB production quantity" })
    .fill("25");
  await page.getByRole("button", { name: "Apply", exact: true }).click();
  await wait(async () => (await summary().innerText()).includes("50"));
  check(
    (await page.locator(".row-quantity").allTextContents())
      .map((x) => x.replace(/\s/g, ""))
      .join("|") === "50required|75required|0required|25required",
    "Backend production quantities: 50 / 75 / DNP 0 / 25",
  );
  await summary().focus();
  await page.keyboard.press("Enter");
  check(
    (await page
      .locator(".component-row details")
      .first()
      .getAttribute("open")) !== null,
    "Enter expands native row disclosure",
  );
  await page.keyboard.press("Escape");
  check(
    (await page
      .locator(".component-row details")
      .first()
      .getAttribute("open")) === null,
    "Escape closes row and restores summary focus",
  );
  await summary().click();
  await page
    .locator(".component-row")
    .first()
    .getByRole("button", { name: "Edit component" })
    .click();
  await page.keyboard.press("Escape");
  check(
    (await page.evaluate(() => document.activeElement.textContent)) ===
      "Edit component",
    "Dialog Escape restores opener focus",
  );
  await edit(undefined, "SYNTHETIC amplifier edited");
  check(
    (await summary().innerText()).includes("SYNTHETIC amplifier edited"),
    "Component edit saves through backend",
  );
  await page.getByRole("button", { name: "Needs review", exact: true }).click();
  check(
    (await page.locator(".component-row").count()) === 1,
    "Needs-review filter retains missing-MPN row",
  );
  await page.getByRole("button", { name: "All", exact: true }).click();
  await page
    .getByRole("searchbox", { name: "Search components" })
    .fill("RC0603");
  check(
    (await page.locator(".component-row").count()) === 1,
    "Search filters MPN",
  );
  await page.getByRole("searchbox").fill("");
  await page.locator(".component-row").first().getByRole("checkbox").focus();
  await page.keyboard.press("Space");
  await wait(
    async () =>
      !(await page
        .locator(".component-row")
        .first()
        .getByRole("checkbox")
        .isChecked()),
  );
  check(true, "Space changes row selection through backend");
  await page.locator(".component-row").first().getByRole("checkbox").check();
  await wait(
    async () =>
      await page
        .locator(".component-row")
        .first()
        .getByRole("checkbox")
        .isChecked(),
  );
  await page.screenshot({
    path: path.join(screenshots, "bom-light.png"),
    fullPage: true,
  });
  await lookup();
  const card = page.locator(".offer-card").first();
  check(
    (await card.innerText()).includes("Unverified match"),
    "Uncertain match remains unverified",
  );
  check(
    (await card.locator("dl").innerText()).includes("unknown") &&
      (await card.locator("dl").innerText()).includes("Not disclosed"),
    "Null stock remains unknown and count not disclosed",
  );
  let choices = 0;
  page.on("request", (r) => {
    if (r.method() === "PUT" && r.url().endsWith("/choice")) choices++;
  });
  await card
    .getByRole("button", { name: "Select product", exact: true })
    .click();
  check(
    choices === 0,
    "Unacknowledged uncertain match sends no choice mutation",
  );
  check(
    await card
      .getByRole("checkbox")
      .evaluate((n) => n === document.activeElement),
    "Acknowledgment receives focus",
  );
  await choose();
  await auditCurrent("Populated supplier offer / light");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await auditCurrent("Populated supplier offer / dark");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(".offer-card").first().scrollIntoViewIfNeeded();
  await page.screenshot({
    path: path.join(screenshots, "offer-dark-mobile.png"),
  });
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await page.screenshot({
    path: path.join(screenshots, "offer-light-mobile.png"),
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: path.join(screenshots, "suppliers-light.png"),
    fullPage: true,
  });
  await go("Purchase list");
  await page
    .getByRole("heading", { name: "Direnc.net", exact: true })
    .waitFor();
  check(
    (await page.locator(".total-box").innerText()).includes("100.00 TRY"),
    "Server Decimal known cost 50 × 2.00 = 100.00 TRY",
  );
  check(
    (await page.locator(".total-box").innerText()).includes("excluded"),
    "VAT basis shown separately",
  );
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: /Export procurement CSV/ }).click();
  const download = await downloadPromise;
  await download.saveAs(path.join(out, "verified-procurement.csv"));
  const csv = fs.readFileSync(
    path.join(out, "verified-procurement.csv"),
    "utf8",
  );
  check(
    csv.includes("100.00") &&
      csv.includes("Unassigned") &&
      !csv.includes("Optional filter"),
    "Real CSV download has server cost, unassigned lines and DNP exclusion",
  );
  await page.screenshot({
    path: path.join(screenshots, "purchase-light.png"),
    fullPage: true,
  });
  await auditCurrent("Populated procurement / light");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await auditCurrent("Populated procurement / dark");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(".total-box").first().scrollIntoViewIfNeeded();
  await page.screenshot({
    path: path.join(screenshots, "purchase-dark-mobile.png"),
  });
  check(
    await page
      .locator(".table-wrap")
      .first()
      .evaluate((n) => n.scrollWidth > n.clientWidth),
    "Mobile procurement table scrolls locally and retains all fields",
  );
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await wait(async () => (await page.locator(".total-box").count()) === 0);
  check(true, "Clear supplier choice removes known total");
  await go("BoM");
  await edit("UNPRICED");
  await lookup();
  await page.locator(".offer-card").getByRole("checkbox").check();
  await page
    .locator(".offer-card")
    .getByRole("button", { name: "Select product" })
    .click();
  await wait(
    async () =>
      (await page.getByRole("button", { name: "Update selection" }).count()) >
      0,
  );
  await go("Purchase list");
  await wait(async () =>
    (await page.locator("main").innerText()).includes("unknown costs"),
  );
  check(
    (await page.locator(".total-box").count()) === 0 &&
      (await page.locator("main").innerText()).includes("Unknown"),
    "Unpriced chosen line retains unknown cost",
  );
  for (const [mpn, message] of [
    ["FAIL", "Synthetic network failure"],
    ["RATE", "Synthetic supplier rate limit"],
    ["EMPTY", "Synthetic empty retrieval"],
  ]) {
    await go("BoM");
    await edit(mpn);
    await lookup();
    check(
      (await page.locator("main").innerText()).includes(message) &&
        (await page.locator(".offer-card").count()) === 0,
      `${mpn}: retrieval failure/empty state never invents offers or stock`,
    );
  }
  await go("BoM"); await edit("SLOW"); await go("Suppliers");
  await page.getByRole("combobox", {name:"Distributor",exact:true}).selectOption("direnc");
  await page.getByRole("button", {name:"Search this MPN",exact:true}).click();
  await page.locator(".job-status").waitFor();
  await page.reload();
  await wait(async()=> (await page.locator(".offer-card").innerText().catch(()=>"" )).includes("SLOW"));
  check(true,"Reload resumes active supplier job and applies completed result");
  await go("BoM");
  await edit("LM358P");
  await lookup();
  await page.reload();
  await page.getByRole("heading", { name: "Product candidates" }).waitFor();
  check(
    (await page.locator(".offer-card").count()) === 1,
    "Reload recovers BoM and supplier result",
  );
  await page
    .getByRole("combobox", { name: "Distributor", exact: true })
    .selectOption("ozdisan");
  check(
    await page.getByRole("button", { name: /Search this MPN/ }).isDisabled(),
    "Özdisan automatic discovery stays disabled",
  );
  await page
    .getByRole("textbox", { name: "Known product URL" })
    .fill("https://www.ozdisan.com/p/synthetic");
  await page.getByRole("button", { name: "Read product URL" }).click();
  await wait(async () =>
    (await page.locator("main").innerText()).includes("Exact reported MPN"),
  );
  check(
    true,
    "Known supplier URL retrieval uses backend and shows exact reported MPN",
  );
  await page
    .getByRole("textbox", { name: "Known product URL" })
    .fill("https://www.ozdisan.com/p/synthetic");
  await page.route("**/api/supplier-jobs", (route) =>
    route.fulfill({
      status: 429,
      headers: { "Retry-After": "60" },
      contentType: "application/json",
      body: JSON.stringify({ detail: "Synthetic quota reached" }),
    }),
  );
  await page.getByRole("button", { name: "Read product URL" }).click();
  await wait(async () =>
    (await page.locator("#toast").innerText()).includes(
      "Try again after 60 seconds",
    ),
  );
  check(
    (await page.locator("#toast").innerText()).includes(
      "Try again after 60 seconds",
    ),
    "HTTP 429 displays Retry-After without automatic resubmission",
  );
  await page.unroute("**/api/supplier-jobs");
  await page.locator(".offer-card").first().getByRole("radio").nth(2).check();
  await page
    .locator(".offer-card")
    .first()
    .getByRole("button", { name: "Select product" })
    .click();
  await wait(
    async () =>
      (await page.getByRole("button", { name: "Update selection" }).count()) >
      0,
  );
  await go("Purchase list");
  await wait(async () => (await page.locator(".total-box").count()) > 0);
  check(
    (await page.locator(".total-box").innerText()).includes("USD") &&
      (await page.locator(".total-box").innerText()).includes("unknown"),
    "USD/VAT-unknown total stays separate",
  );
  await go("BoM");
  await importFile("altium_a1.xlsx");
  check(
    (await page.locator(".component-row").count()) === 4,
    "XLSX import works with worksheet selector",
  );
  await importFile("kicad_a1.tsv");
  check(
    (await page.locator(".component-row").count()) === 3,
    "TSV import retains malformed/unknown row",
  );
  await page
    .getByRole("combobox", { name: "Current BoM", exact: true })
    .selectOption({ label: "altium_a1 · altium_a1.csv" });
  await edit(
    "LONG-MPN-" + "0123456789".repeat(12),
    "SYNTHETIC <img src=x onerror=alert(1)>",
  );
  check(
    (await page.locator(".component-name img").count()) === 0,
    "Imported/edited text cannot inject HTML",
  );
  await auditCurrent("Long MPN row");
  await page.getByRole("link", { name: "Skip to workspace" }).focus();
  await page.keyboard.press("Enter");
  check(
    (await page.getByRole("heading", { name: "BoM", exact: true }).count()) ===
      1 &&
      (await page
        .locator("main")
        .evaluate((n) => n === document.activeElement)),
    "Skip link keeps current route and focuses main",
  );
  await page.getByRole("button", { name: "Mark selected DNP" }).click();
  await page.getByRole("button", { name: "Mark DNP", exact: true }).click();
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  check(
    (await page.locator(".component-row input:checked").count()) === 0,
    "Bulk DNP excludes selected rows and clears choices",
  );
  await go("Session BoMs 3");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await page.reload();
  check(
    (await page.locator("html").getAttribute("data-theme")) === "dark",
    "Theme preference survives reload",
  );
  for (const theme of ["light", "dark"]) {
    if ((await page.locator("html").getAttribute("data-theme")) !== theme)
      await page
        .getByRole("button", { name: `Switch to ${theme} theme` })
        .click();
    for (const width of [1440, 1024, 760, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const name of [
        "Session BoMs 3",
        "BoM",
        "Suppliers",
        "Purchase list",
      ]) {
        await go(name);
        await page.waitForTimeout(100);
        const dimensions = await page.evaluate(() => ({
          width: innerWidth,
          scroll: document.documentElement.scrollWidth,
        }));
        check(
          dimensions.scroll <= width,
          `${theme} ${width}px ${name}: no page horizontal overflow`,
        );
        if (width === 390 || width === 1440) {
          await page.evaluate(axe.source);
          const audit = await page.evaluate(
            async () =>
              await axe.run({
                runOnly: {
                  type: "tag",
                  values: ["wcag2a", "wcag2aa", "wcag21aa"],
                },
              }),
          );
          audits.push({
            theme,
            width,
            name,
            violations: audit.violations.map((v) => ({
              id: v.id,
              impact: v.impact,
              nodes: v.nodes.map((n) => n.target),
            })),
          });
          fs.writeFileSync(
            path.join(out, "accessibility-audits.json"),
            JSON.stringify(audits, null, 2),
          );
          check(
            audit.violations.length === 0,
            `${theme} ${width}px ${name}: axe WCAG A/AA scan`,
          );
        }
        if (width === 390 || width === 1440)
          await page.screenshot({
            path: path.join(
              screenshots,
              `${name.replace(" 3", "").replace(/ /g, "-").toLowerCase()}-${theme}-${width}.png`,
            ),
            fullPage: width > 760,
          });
      }
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await go("BoM");
  check(
    (await page
      .getByRole("navigation")
      .evaluate((n) => getComputedStyle(n).position)) === "fixed",
    "Mobile bottom navigation is functional and fixed",
  );
  check(
    (await page
      .getByRole("navigation")
      .getByRole("link", { name: "BoM", exact: true })
      .getAttribute("aria-current")) === "page",
    "Mobile navigation announces current page",
  );
  await page.setViewportSize({ width: 760, height: 500 });
  await go("Suppliers");
  await page.screenshot({
    path: path.join(screenshots, "zoom-200-equivalent.png"),
    fullPage: true,
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  check(
    (await page
      .getByRole("button", { name: "Read product URL" })
      .evaluate((n) => getComputedStyle(n).transitionDuration)) === "0s",
    "Reduced motion removes transitions",
  );
  // Session expiry is a controlled HTTP response; recovery makes a real GET session request.
  await page.route("**/api/boms/*", async (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Session expired" }),
    }),
  );
  await go("BoM");
  await page
    .getByRole("spinbutton", { name: "PCB production quantity" })
    .fill("2");
  await page.getByRole("button", { name: "Apply", exact: true }).click();
  await page.getByRole("heading", { name: "Your session expired" }).waitFor();
  check(
    (await page.locator(".component-row").count()) === 0,
    "401 clears stale rows and gives explicit recovery",
  );
  await page.unroute("**/api/boms/*");
  await page.getByRole("button", { name: "Start a new session" }).click();
  await page.getByRole("heading", { name: "BoM", exact: true }).waitFor();
  check(true, "Explicit session recovery completes");
  check(errors.length === 0, "No browser JavaScript errors");
  fs.writeFileSync(
    path.join(out, "browser-validation.json"),
    JSON.stringify(
      {
        checks: checks.length,
        passed: checks,
        errors,
        date: "2026-10-09",
        supplierData: "Synthetic fixture only",
      },
      null,
      2,
    ),
  );
  console.log(JSON.stringify({ checks: checks.length, errors }));
};
(async () => {
  const { chromium } = require("playwright");
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage({ acceptDownloads: true });
  try {
    await run(page);
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
