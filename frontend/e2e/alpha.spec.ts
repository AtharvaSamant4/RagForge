import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

test.skip(!process.env.QA_ALPHA, "Private-alpha stack only");
const root = path.resolve("..");
const compose = [
  "compose",
  "--env-file",
  ".env.alpha",
  "-p",
  "ragforge-m4-alpha",
  "-f",
  "compose.yaml",
  "-f",
  "compose.alpha.yaml",
];
let workerPaused = false;
const operate = (...args: string[]) =>
  execFileSync("docker", [...compose, ...args], { cwd: root, stdio: "pipe" });
test.afterEach(() => {
  if (workerPaused) {
    operate("up", "-d", "--no-deps", "worker");
    workerPaused = false;
  }
});

test("invite-only alpha, quota errors, cited answers, export and expired session", async ({
  page,
  context,
  baseURL,
}, info) => {
  test.setTimeout(240_000);
  const credentials = JSON.parse(
    fs.readFileSync(
      path.join(root, "artifacts/m4-private-credentials.json"),
      "utf8",
    ),
  );
  const email = `alpha-browser-${info.project.name}-${Date.now()}@example.com`;
  const password = "private-alpha-browser-fixture-password";
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const screenshot = async (name: string) => {
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    await page.screenshot({
      path: path.join(
        root,
        `docs/qa/screenshots/alpha-${info.project.name}-${name}.png`,
      ),
      fullPage: true,
    });
  };
  const nav = async (name: string) => {
    if (info.project.name === "mobile")
      await page.getByLabel("Workspace section").selectOption({ label: name });
    else
      await page
        .getByRole("navigation")
        .getByRole("button", {
          name: name === "Documents" ? /^Documents(?:\s+\d+)?$/ : name,
          exact: name !== "Documents",
        })
        .click();
  };
  await page.goto("/");
  await expect(page.getByLabel("Invitation code")).toBeVisible();
  await screenshot("invitation");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Invitation code").fill("invalid-fixture-invitation");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page.locator(".alert.error")).toContainText(
    "valid, unused invitation",
  );
  await page
    .getByLabel("Invitation code")
    .fill(credentials[info.project.name + "_invite"]);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Make your knowledge useful." }),
  ).toBeVisible();
  const cookie = (await context.cookies()).find(
    (c) => c.name === "ragforge_session",
  );
  expect(cookie?.secure && cookie?.httpOnly).toBe(true);
  await page
    .getByRole("main")
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Project name", { exact: true })
    .fill("Private alpha browser QA");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Documents", exact: true }),
  ).toBeVisible();
  await expect(page.locator("#project-select")).toHaveValue(/[a-f0-9-]{36}/);
  const project = await page.locator("#project-select").inputValue();
  await page
    .locator('input[type="file"]')
    .setInputFiles(path.join(root, "samples/acme-handbook.pdf"));
  await expect(page.locator("tbody .status").first()).toHaveText(
    /queued|processing|ready/,
  );
  await expect(page.locator("tbody .status").first()).toHaveText("ready");
  await page.locator('input[type="file"]').setInputFiles({
    name: "invalid.exe",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("MZ"),
  });
  await expect(page.locator(".alert.error")).toContainText("Supported files");
  await page.getByRole("button", { name: "Dismiss error" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "malformed.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.7\nmalformed-private-fixture"),
  });
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: "malformed.pdf" })
      .locator(".status"),
  ).toHaveText("failed");
  await screenshot("failed-upload");
  operate("stop", "worker");
  workerPaused = true;
  try {
    for (let i = 0; i < 4; i++) {
      await page.locator('input[type="file"]').setInputFiles({
        name: `queued-${i}.txt`,
        mimeType: "text/plain",
        buffer: Buffer.from(
          "Queue quota fixture. The sample is deliberately small.",
        ),
      });
      await expect(
        page
          .getByRole("row")
          .filter({ hasText: `queued-${i}.txt` })
          .locator(".status"),
      ).toHaveText("queued");
    }
    await page.locator('input[type="file"]').setInputFiles({
      name: "quota.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Rejected by the real account quota."),
    });
    await expect(page.locator(".alert.error")).toContainText(
      "ingestion-job quota reached",
    );
    await screenshot("quota");
  } finally {
    operate("up", "-d", "--no-deps", "worker");
    workerPaused = false;
  }
  await page.getByRole("button", { name: "Dismiss error" }).click();
  await expect(
    page.locator("tbody .status").filter({ hasText: /^ready$/ }),
  ).toHaveCount(5, { timeout: 90_000 });
  await nav("Playground");
  await page.getByLabel("Your question").fill("What is the refund period?");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.locator(".answer-text").last()).toContainText("30 day");
  await expect(page.locator(".thinking")).toHaveCount(0);
  await page.locator(".citations .source summary").first().click();
  await expect(page.locator(".citations .source p").first()).toBeVisible();
  const quote = page.locator(".citations .source p").first();
  await quote.scrollIntoViewIfNeeded();
  const quoteBounds = await quote.boundingBox();
  const composerBounds = await page.locator(".chat-composer").boundingBox();
  expect(quoteBounds!.y + quoteBounds!.height).toBeLessThanOrEqual(
    composerBounds!.y + 1,
  );
  await screenshot("citations");
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
  await page
    .getByRole("button", { name: "Run evaluation", exact: true })
    .click();
  await expect(page.locator(".evaluation-run")).toHaveCount(1);
  await screenshot("evaluation");
  await nav("Deployment");
  const panel = page.getByRole("region", {
    name: "Standalone application export",
  });
  await panel.getByLabel("Include selected knowledge snapshot").check();
  await panel.getByLabel(/acme-handbook.pdf ·/).check();
  await panel
    .getByLabel(
      "I approve including these documents and understand exported copies cannot be revoked.",
    )
    .check();
  await panel
    .getByRole("button", { name: "Export standalone application", exact: true })
    .click();
  await expect(panel).toContainText("Export status: ready");
  const download = page.waitForEvent("download");
  await panel
    .getByRole("button", { name: "Download ZIP", exact: true })
    .click();
  await (
    await download
  ).saveAs(path.join(root, `artifacts/browser/alpha-${info.project.name}.zip`));
  await page.getByLabel("Enable public query access for this project").check();
  await page
    .getByLabel("Allowed website origins (one per line)")
    .fill("https://pilot.example");
  await page
    .getByRole("button", { name: "Save and rotate public token" })
    .click();
  await expect(page.locator(".alert.error")).toContainText(
    "disabled by the operator",
  );
  await page.getByRole("button", { name: "Dismiss error" }).click();
  await screenshot("export");
  await page.getByRole("button", { name: /Sign out/ }).click();
  await expect(page.getByLabel("Email", { exact: true })).toBeVisible();
  // The form defaults to registration after logout; explicitly select sign in.
  if (await page.getByLabel("Invitation code").count())
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator("#project-select")).toBeVisible();
  await nav("Playground");
  execFileSync(
    "docker",
    [
      ...compose,
      "exec",
      "-T",
      "api",
      "python",
      "-c",
      "import sys,time;from sqlalchemy import select,update;from app.db import SessionLocal;from app.models import User,LoginSession;email=sys.stdin.read().strip();\nwith SessionLocal() as db:\n db.execute(update(LoginSession).where(LoginSession.user_id.in_(select(User.id).where(User.email==email))).values(expires_at=time.time()-1));db.commit()",
    ],
    { cwd: root, input: email, stdio: ["pipe", "pipe", "pipe"] },
  );
  await page.getByLabel("Your question").fill("What is the refund period?");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back." }),
  ).toBeVisible();
  await expect(page.locator(".alert.error")).toContainText(/session|sign in/i);
  await screenshot("expired-session");
  expect(errors).toEqual([]);
});
