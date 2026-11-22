import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test.skip(
  !process.env.QA_PILOT,
  "Explicit engineering-only pilot QA deployment required",
);
const root = path.resolve("..");
const credentials = () =>
  JSON.parse(
    fs.readFileSync(
      path.join(root, "artifacts/m5-pilot-credentials.json"),
      "utf8",
    ),
  );

async function login(page: Page, email: string, password: string) {
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: /Build something grounded\.|Welcome back\./,
    }),
  ).toBeVisible();
  if (
    await page
      .getByRole("heading", { name: "Build something grounded." })
      .isVisible()
  )
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Sign in", exact: true })
    .first()
    .click();
  await expect(page.locator(".main-shell")).toBeVisible();
}
async function navigate(page: Page, mobile: boolean, name: string) {
  if (mobile)
    await page.getByLabel("Workspace section").selectOption({ label: name });
  else
    await page
      .getByRole("navigation")
      .getByRole("button", { name, exact: true })
      .click();
}
async function signout(page: Page, mobile: boolean) {
  await page.locator(mobile ? ".mobile-logout" : ".profile").click();
  await expect(page.getByLabel("Email", { exact: true })).toBeVisible();
}

test("optional pilot consent, private feedback, operator triage and deletion", async ({
  page,
}, info) => {
  test.setTimeout(240_000);
  const c = credentials(),
    profile = info.project.name,
    mobile = profile === "mobile";
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const capture = async (name: string) => {
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    fs.mkdirSync(path.join(root, "docs/qa/screenshots/m5"), {
      recursive: true,
    });
    await page.screenshot({
      path: path.join(root, `docs/qa/screenshots/m5/${profile}-${name}.png`),
      fullPage: true,
    });
  };
  await login(page, c[profile + "_email"], c[profile + "_password"]);
  await navigate(page, mobile, "Pilot study");
  await expect(
    page.getByRole("heading", { name: "Your privacy and consent" }),
  ).toBeVisible();
  const start = page.getByRole("button", {
    name: "Start optional pilot collection",
  });
  await expect(start).toBeDisabled();
  expect((await page.request.get("/api/v1/admin/pilot/report")).status()).toBe(
    403,
  );
  await page
    .getByLabel(
      "I consent to optional pilot technical telemetry and the feedback I choose to submit.",
    )
    .check();
  await start.click();
  await expect(page.getByRole("status")).toContainText("Consent saved");
  const state = await (await page.request.get("/api/v1/pilot/me")).json();
  expect(state.cohort).toBe("engineering_qa");
  expect(
    state.funnel.stages.filter((s: { completed: boolean }) => s.completed),
  ).toHaveLength(1);
  await page
    .getByRole("combobox", { name: "Study task", exact: true })
    .selectOption("2");
  await page
    .getByRole("combobox", { name: "Completion status", exact: true })
    .selectOption("failed");
  await page.getByLabel("Time taken in seconds", { exact: true }).fill("75");
  await page.getByLabel("Number of errors", { exact: true }).fill("2");
  await page
    .getByLabel("Times assistance requested", { exact: true })
    .fill("1");
  await page
    .getByRole("combobox", {
      name: "Difficulty (1 easy to 5 hard)",
      exact: true,
    })
    .selectOption("4");
  const privateText =
    "Synthetic engineering QA feedback only; no real participant or testimonial.";
  await page
    .getByLabel(
      "Optional feedback — what happened, and would you use this again?",
    )
    .fill(privateText);
  await page.getByRole("button", { name: "Save task outcome" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Self-reported task outcome saved",
  );
  await page
    .getByRole("combobox", { name: "Problem category", exact: true })
    .selectOption("setup");
  await page
    .getByLabel("Private reproduction without secrets")
    .fill(privateText);
  await page.getByRole("button", { name: "Submit private problem" }).click();
  await expect(page.getByRole("status")).toContainText("Nothing was published");
  await capture("participant-feedback");
  await signout(page, mobile);
  await login(page, c.admin_email, c.admin_password);
  await navigate(page, mobile, "Pilot study");
  await expect(
    page.getByRole("heading", { name: "Pilot operator dashboard" }),
  ).toBeVisible();
  await expect(
    page.getByText("Activated: 0 · Operator-attested real trials: 0", {
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Report cohort", exact: true })
    .selectOption("engineering_qa");
  await page
    .getByRole("button", {
      name: `Review feedback ${state.participant_id.slice(0, 8)}`,
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("heading", { name: "Private operator review" }),
  ).toBeVisible();
  await expect(page.getByRole("main")).toContainText(privateText);
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", {
      name: "Download sanitized pilot report",
      exact: true,
    })
    .click();
  const reportPath = path.join(
    root,
    `artifacts/browser/m5-${profile}-sanitized-report.json`,
  );
  await (await download).saveAs(reportPath);
  const report = fs.readFileSync(reportPath, "utf8");
  expect(report).not.toContain(privateText);
  expect(report).not.toContain(c[profile + "_email"]);
  expect(JSON.parse(report).operator_attested_real_trials).toBe(0);
  await page
    .getByRole("button", { name: /Triage report/ })
    .first()
    .click();
  await page
    .getByRole("combobox", { name: "Severity", exact: true })
    .selectOption("high");
  await page
    .getByLabel("Engineering work reference", { exact: true })
    .fill("QA-PILOT-1");
  await page
    .getByLabel("Manually sanitized reproduction", { exact: true })
    .fill(
      "In a disposable QA workspace, upload the public sample and observe a setup failure.",
    );
  await page
    .getByLabel(
      "I reviewed this text for confidential material and approve downloading it.",
    )
    .check();
  await page
    .getByRole("button", { name: "Save issue triage", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "No GitHub issue was created",
  );
  const issueDownload = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download reviewed issue", exact: true })
    .click();
  const issuePath = path.join(
    root,
    `artifacts/browser/m5-${profile}-reviewed-issue.json`,
  );
  await (await issueDownload).saveAs(issuePath);
  expect(fs.readFileSync(issuePath, "utf8")).not.toContain(privateText);
  await capture("operator-dashboard");
  await signout(page, mobile);
  await login(page, c[profile + "_email"], c[profile + "_password"]);
  await navigate(page, mobile, "Pilot study");
  await page
    .getByRole("button", {
      name: "Withdraw consent and erase pilot records",
      exact: true,
    })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "prior pilot activity/feedback deleted",
  );
  const withdrawn = await (await page.request.get("/api/v1/pilot/me")).json();
  expect(withdrawn.consented_at).toBeNull();
  expect(withdrawn.tasks).toEqual([]);
  expect(
    withdrawn.funnel.stages.every((s: { completed: boolean }) => !s.completed),
  ).toBe(true);
  await page
    .getByRole("button", {
      name: "Delete pilot enrollment and data",
      exact: true,
    })
    .click();
  await expect(page.getByRole("main")).toContainText("You are not enrolled");
  await capture("deleted-pilot-data");
  expect(errors).toEqual([]);
});

test("explicit import of real independent runtime evidence", async ({
  page,
}, info) => {
  const c = credentials(),
    mobile = info.project.name === "mobile";
  await login(page, c.runtime_email, c.runtime_password);
  await navigate(page, mobile, "Pilot study");
  await page
    .getByLabel("Runtime evidence JSON")
    .setInputFiles(c.runtime_proof_path);
  await page
    .getByRole("button", { name: "Verify runtime evidence", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Signed runtime evidence verified",
  );
  const state = await (await page.request.get("/api/v1/pilot/me")).json();
  expect(
    state.funnel.stages.every((s: { completed: boolean }) => s.completed),
  ).toBe(true);
  expect(
    state.funnel.time_to_observed_standalone_deployment_seconds,
  ).toBeGreaterThan(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
  fs.mkdirSync(path.join(root, "docs/qa/screenshots/m5"), { recursive: true });
  await page.screenshot({
    path: path.join(
      root,
      `docs/qa/screenshots/m5/${info.project.name}-runtime-evidence.png`,
    ),
    fullPage: true,
  });
});
