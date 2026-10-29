import { expect, test, type Page } from "@playwright/test";

const INTERVIEWER_EMAIL = "demo@example.com";
const INTERVIEWER_PASSWORD = "DemoPass123!";

async function removeInterview(page: Page, sessionId: string) {
  if (!sessionId) return;
  await page.evaluate(async (id) => {
    const storedSession = Object.values(localStorage)
      .map((value) => {
        try { return JSON.parse(value); } catch { return null; }
      })
      .find((value) => typeof value?.access_token === "string");
    if (!storedSession) throw new Error("The interviewer auth session was not found");
    const response = await fetch(`/rest/v1/interview_sessions?id=eq.${encodeURIComponent(id)}`, {
      method: "DELETE",
      headers: {
        apikey: "sb_publishable_local_demo",
        Authorization: `Bearer ${storedSession.access_token}`,
      },
    });
    if (!response.ok) throw new Error(`Cleanup failed with HTTP ${response.status}`);
  }, sessionId);
}

test("candidate canvas changes are synchronized with the interviewer", async ({ browser }) => {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  const title = `E2E collaboration ${suffix}`;
  const candidateName = `Candidate ${suffix.slice(-6)}`;

  const interviewerContext = await browser.newContext();
  const candidateContext = await browser.newContext();
  const interviewer = await interviewerContext.newPage();
  const candidate = await candidateContext.newPage();
  let sessionId = "";

  try {
    await test.step("log in as the interviewer", async () => {
      await interviewer.goto("/auth");
      await interviewer.getByLabel("Email").fill(INTERVIEWER_EMAIL);
      await interviewer.getByLabel("Password").fill(INTERVIEWER_PASSWORD);
      await interviewer.getByRole("button", { name: "Sign in", exact: true }).click();
      await expect(interviewer).toHaveURL(/\/dashboard$/);
    });

    await test.step("create and start an interview session", async () => {
      await interviewer.getByRole("button", { name: "New interview" }).click();
      await interviewer.getByLabel("Title").fill(title);
      await interviewer.getByLabel("Prompt for the candidate").fill("Add a service to the shared system design canvas.");
      await interviewer.getByRole("button", { name: "Create", exact: true }).click();
      await expect(interviewer.getByText(title, { exact: true })).toBeVisible();
      sessionId = new URL(interviewer.url()).pathname.split("/").at(-1) ?? "";
      await interviewer.getByRole("button", { name: "Start", exact: true }).click();
      await expect(interviewer.getByRole("button", { name: "End", exact: true })).toBeVisible();
    });

    let joinLink = "";
    await test.step("share the candidate join link", async () => {
      await interviewer.getByRole("button", { name: "Invite" }).click();
      joinLink = (await interviewer.getByTestId("candidate-join-link").textContent())?.trim() ?? "";
      expect(joinLink).toMatch(/\/join\/[a-zA-Z0-9_-]+$/);
    });

    await test.step("join from a separate candidate browser session", async () => {
      await candidate.goto(joinLink);
      await candidate.getByPlaceholder("Your name").fill(candidateName);
      await candidate.getByRole("button", { name: "Join interview" }).click();
      await expect(candidate.getByTestId("canvas-surface")).toBeVisible();
      await expect(candidate.getByRole("button", { name: "Add Service component" })).toBeVisible();
    });

    await test.step("change the canvas as the candidate", async () => {
      await candidate.getByRole("button", { name: "Add Service component" }).click();
      const canvas = candidate.getByTestId("canvas-surface");
      await canvas.click({ position: { x: 720, y: 320 } });
      await expect(candidate.getByTestId("canvas-node").filter({ hasText: "Service" })).toHaveCount(1);
      await expect(candidate.getByText("Saved", { exact: true })).toBeVisible();
    });

    await test.step("verify that the interviewer receives the canvas change", async () => {
      await expect(interviewer.getByTestId("canvas-node").filter({ hasText: "Service" })).toHaveCount(1);
    });
  } finally {
    await removeInterview(interviewer, sessionId);
    await candidateContext.close();
    await interviewerContext.close();
  }
});
