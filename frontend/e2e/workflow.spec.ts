import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import http from "node:http";

let fixtureServer: http.Server | undefined;
test.afterEach(async () => {
  if (fixtureServer) {
    fixtureServer.closeAllConnections();
    await new Promise<void>((resolve) => fixtureServer!.close(() => resolve()));
    fixtureServer = undefined;
  }
});

test("complete knowledge workspace and public widget workflow", async ({
  page,
  context,
  baseURL,
}, testInfo) => {
  test.setTimeout(240_000);
  test.skip(
    Boolean(process.env.QA_ALPHA),
    "Development widget workflow runs separately",
  );
  const email = `browser-${testInfo.project.name}-${Date.now()}@example.com`,
    password = "browser-test-password-long";
  const prefix = testInfo.project.name,
    screenshotDir = path.resolve("../docs/qa/screenshots/m4-development");
  fs.mkdirSync(screenshotDir, { recursive: true });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const screenshot = async (name: string) => {
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect
      .poll(
        () =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth + 1,
          ),
        { message: "No page-level horizontal overflow" },
      )
      .toBe(true);
    await page.screenshot({
      path: path.join(screenshotDir, `${prefix}-${name}.png`),
      fullPage: true,
    });
  };
  const nav = async (name: string) => {
    if (testInfo.project.name === "mobile")
      await page.getByLabel("Workspace section").selectOption({ label: name });
    else
      await page
        .getByRole("navigation")
        .getByRole(
          "button",
          name === "Documents"
            ? { name: /^Documents(?:\s+\d+)?$/ }
            : { name, exact: true },
        )
        .click();
  };
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Build something grounded." }),
  ).toBeVisible();
  await screenshot("registration");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Make your knowledge useful." }),
  ).toBeVisible();
  await page
    .getByRole("main")
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Project name", { exact: true })
    .fill(`Browser ${prefix} knowledge`);
  await dialog
    .getByLabel("Description (optional)")
    .fill("Disposable browser workflow fixture");
  await dialog
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Documents", exact: true }),
  ).toBeVisible();
  const projectId = await page.locator("#project-select").inputValue();
  await page
    .locator('input[type="file"]')
    .setInputFiles(path.resolve("../samples/acme-handbook.pdf"));
  await expect(page.locator("tbody .status").first()).toHaveText(
    /queued|processing|ready/,
  );
  await expect(page.locator("tbody .status").first()).toHaveText("ready");
  await screenshot("documents");
  await page.getByRole("button", { name: /acme-handbook.pdf PDF/ }).click();
  await expect(page.getByRole("dialog")).toContainText("30 day refund");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.locator('input[type="file"]').setInputFiles({
    name: "unsupported.exe",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("MZ"),
  });
  await expect(page.locator(".alert.error")).toContainText("Supported files");
  await page.getByRole("button", { name: "Dismiss error" }).click();
  await nav("Playground");
  await page.getByLabel("Your question").fill("What is the refund period?");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.locator(".answer-text").last()).toContainText("30 day");
  await page.locator(".citations .source summary").first().click();
  await expect(page.locator(".citations .source p").first()).toBeVisible();
  await page.getByLabel("Show retrieval").check();
  await expect(page.locator(".retrieval")).toBeVisible();
  await screenshot("playground");
  await page
    .getByLabel("Your question")
    .fill("Who won the Martian election in 2050?");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.locator(".answer-text").last()).toContainText(
    "couldn't find enough",
  );
  await nav("Pipeline");
  await expect(
    page.getByText("sentence-transformers/all-MiniLM-L6-v2", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Chunk size (words)").fill("140");
  await page.getByRole("button", { name: "Save configuration" }).click();
  await expect(page.getByRole("status").first()).toContainText(
    "Pipeline saved",
  );
  await page.getByRole("button", { name: "Rebuild index" }).click();
  await expect(page.locator(".model-name").locator("..")).toContainText(
    "generation 1",
  );
  await expect(
    page.locator(".model-name").locator("..").locator(".status"),
  ).toHaveText("ready");
  await expect(
    page.getByText("Your chunk settings match the indexed sources.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByText("Compare retrieval strategies", { exact: true }).click();
  await page
    .getByLabel("Comparison question")
    .fill("What is the refund period?");
  await page
    .getByRole("button", { name: "Compare strategies", exact: true })
    .click();
  await expect(page.locator(".comparison-result")).toHaveCount(3);
  await screenshot("pipeline");
  await nav("Evaluation");
  await page
    .getByLabel("Question", { exact: true })
    .fill("What is the refund period?");
  await page
    .getByLabel("Relevant source")
    .selectOption({ label: "acme-handbook.pdf" });
  await page
    .getByLabel("Expected answer (optional)")
    .fill("30 day refund period");
  await page.getByRole("button", { name: "Add verified case" }).click();
  await expect(page.locator(".eval-cases")).toContainText(
    "What is the refund period?",
  );
  await page
    .getByRole("button", { name: "Run evaluation", exact: true })
    .click();
  await expect(page.locator(".evaluation-run")).toHaveCount(1);
  await expect(page.locator(".evaluation-run")).toContainText("100%");
  await screenshot("evaluation");
  await nav("API & Integration");
  await page.getByLabel("Key name").fill("Browser fixture key");
  await page.getByRole("button", { name: "Create API key" }).click();
  const secret = await page.locator(".secret-box>code").textContent();
  expect(secret).toMatch(/^rf_/);
  const response = await context.request.post(
    `${baseURL}/api/v1/projects/${projectId}/query`,
    {
      headers: { Authorization: `Bearer ${secret}` },
      data: { question: "What is the refund period?" },
    },
  );
  expect(response.ok()).toBe(true);
  expect((await response.json()).citations.length).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Dismiss secret" }).click();
  await nav("Deployment");
  const exportPanel = page.getByRole("region", {
    name: "Standalone application export",
  });
  await expect(
    exportPanel.getByLabel(
      "Configuration only · no uploaded documents (default)",
    ),
  ).toBeChecked();
  await exportPanel
    .getByRole("button", { name: "Export standalone application", exact: true })
    .click();
  await expect(exportPanel).toContainText("Export status: ready");
  const configDownloadPromise = page.waitForEvent("download");
  await exportPanel
    .getByRole("button", { name: "Download ZIP", exact: true })
    .click();
  const configDownload = await configDownloadPromise;
  await configDownload.saveAs(
    path.resolve(`../artifacts/browser/m4-${prefix}-configuration.zip`),
  );
  await exportPanel.getByLabel("Include selected knowledge snapshot").check();
  await expect(
    exportPanel.getByRole("button", {
      name: "Export standalone application",
      exact: true,
    }),
  ).toBeDisabled();
  await exportPanel.getByLabel(/acme-handbook.pdf ·/).check();
  await exportPanel
    .getByLabel(
      "I approve including these documents and understand exported copies cannot be revoked.",
    )
    .check();
  const beforeExport = [];
  for (const question of [
    "What is the refund period?",
    "How long does a refund take?",
    "Who won the Martian election in 2050?",
  ]) {
    const original = await context.request.post(
      `${baseURL}/api/v1/projects/${projectId}/query`,
      { data: { question }, headers: { Origin: baseURL! } },
    );
    expect(original.ok()).toBe(true);
    beforeExport.push({ question, result: await original.json() });
  }
  await exportPanel
    .getByRole("button", { name: "Export standalone application", exact: true })
    .click();
  await expect(exportPanel).toContainText("Export status: ready");
  await expect(exportPanel).toContainText("1 included documents");
  const snapshotDownloadPromise = page.waitForEvent("download");
  await exportPanel
    .getByRole("button", { name: "Download ZIP", exact: true })
    .click();
  const snapshotDownload = await snapshotDownloadPromise;
  await snapshotDownload.saveAs(
    path.resolve(`../artifacts/browser/m4-${prefix}-snapshot.zip`),
  );
  const exportJobs = await context.request.get(
    `${baseURL}/api/v1/projects/${projectId}/exports`,
  );
  expect(exportJobs.ok()).toBe(true);
  const exportEvidence = (await exportJobs.json())[0];
  fs.writeFileSync(
    path.resolve(`../artifacts/browser/m4-${prefix}-export-before.json`),
    JSON.stringify(
      {
        before: beforeExport,
        source_project_id: projectId,
        export: exportEvidence,
      },
      null,
      2,
    ),
  );
  await screenshot("standalone-export");
  await exportPanel.screenshot({
    path: path.join(screenshotDir, `${prefix}-standalone-export-panel.png`),
  });
  await page.getByLabel("Enable public query access for this project").check();
  await page.getByLabel("Assistant title").fill("Browser knowledge assistant");
  await page
    .getByLabel("Allowed website origins (one per line)")
    .fill("http://localhost:4020");
  await page
    .getByRole("button", { name: "Save and rotate public token" })
    .click();
  const embed = await page.locator(".secret-box pre code").textContent();
  expect(embed).toContain("data-token=");
  const widget = await context.newPage();
  widget.on("requestfailed", (request) =>
    console.log("Widget network failure:", request.failure()?.errorText),
  );
  fixtureServer = http.createServer((_, response) => {
    response.setHeader("Content-Type", "text/html");
    response.end(
      `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><h1>External widget test fixture</h1>${embed}</body></html>`,
    );
  });
  await new Promise<void>((resolve) =>
    fixtureServer!.listen(4020, "127.0.0.1", resolve),
  );
  await widget.goto("http://localhost:4020/");
  await expect(
    widget.getByRole("button", { name: "Open knowledge assistant" }),
  ).toBeVisible({ timeout: 10000 });
  await widget
    .getByRole("button", { name: "Open knowledge assistant" })
    .click();
  const frame = widget.frameLocator('iframe[title="Knowledge assistant"]');
  await expect(
    frame.getByText("Browser knowledge assistant", { exact: true }),
  ).toBeVisible();
  await frame
    .getByLabel("Ask a question", { exact: true })
    .fill("What is the refund period?");
  await frame.getByRole("button", { name: "Send", exact: true }).click();
  await expect(frame.locator("main .assistant").last()).toContainText("30 day");
  await widget.screenshot({
    path: path.join(screenshotDir, `${prefix}-widget.png`),
    fullPage: true,
  });
  await page
    .getByLabel("Enable public query access for this project")
    .uncheck();
  await page.getByRole("button", { name: "Save private state" }).click();
  await expect(page.getByRole("status").first()).toContainText(
    "Widget access disabled",
  );
  await frame
    .getByLabel("Ask a question", { exact: true })
    .fill("What is the refund period?");
  await frame.getByRole("button", { name: "Send", exact: true }).click();
  await expect(frame.locator(".error").last()).toContainText(
    "Published assistant not found",
  );
  await widget.close();
  await nav("Documents");
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Delete acme-handbook.pdf", exact: true })
    .click();
  await expect(page.locator("tbody")).toHaveCount(0);
  await nav("Playground");
  await page.getByLabel("Your question").fill("What is the refund period?");
  await expect(
    page.getByRole("button", { name: "Send question" }),
  ).toBeDisabled();
  await nav("Settings");
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Delete project", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Make your knowledge useful." }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Sign out/ }).click();
  await expect(page.getByLabel("Email", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Make your knowledge useful." }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Sign out/ }).click();
  expect(errors).toEqual([]);
});
