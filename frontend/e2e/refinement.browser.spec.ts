import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const REFINEMENT_DIR = path.resolve(__dirname, "../../qa-artifacts/refinement");

test.describe("Visual Excellence & Design System Refinement QA (Phase 9.2.1)", () => {
  test.beforeAll(async () => {
    if (!fs.existsSync(REFINEMENT_DIR)) {
      fs.mkdirSync(REFINEMENT_DIR, { recursive: true });
    }
  });

  test.beforeEach(async ({ request }) => {
    // Reset mock backend state
    await request.post("http://127.0.0.1:8000/__test_control/reset", { timeout: 10000 });
  });

  test("Capture Desktop (1440x900) & Mobile (390x844) Refinement Artifacts", async ({ page }) => {
    // 1. Initial Authentication Journey
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/connect", { waitUntil: "domcontentloaded", timeout: 10000 });
    await expect(page.getByRole("heading", { name: "Agent Network" })).toBeVisible({ timeout: 10000 });

    const keyInput = page.locator("input[placeholder='asama_live_...']");
    await expect(keyInput).toBeVisible({ timeout: 10000 });
    await keyInput.fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard", { timeout: 10000 });

    // ==========================================
    // 1. DESKTOP VIEWPORT (1440 x 900)
    // ==========================================

    // 1.1 Desktop Dashboard
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/dashboard", { waitUntil: "domcontentloaded", timeout: 10000 });
    const dashHeading = page.getByRole("heading", { name: "Agent Workspace Dashboard" });
    await expect(dashHeading).toBeVisible({ timeout: 10000 });
    await expect(page.locator("body")).toContainText("LiquidityBot-Alpha", { timeout: 10000 });
    await page.screenshot({
      path: path.join(REFINEMENT_DIR, "desktop-dashboard.png"),
      fullPage: false,
    });

    // 1.2 Desktop Feed
    await page.goto("/feed", { waitUntil: "domcontentloaded", timeout: 10000 });
    const feedHeading = page.getByRole("heading", { name: "Opportunity Discovery Feed" });
    await expect(feedHeading).toBeVisible({ timeout: 10000 });
    const firstCard = page.locator("[data-testid='post-card-10000000-0000-0000-0000-000000000001']");
    await expect(firstCard).toBeVisible({ timeout: 10000 });
    await page.screenshot({
      path: path.join(REFINEMENT_DIR, "desktop-feed.png"),
      fullPage: false,
    });

    // 1.3 Desktop Composer Modal
    const publishBtn = page.getByRole("button", { name: "Publish Opportunity" });
    await expect(publishBtn).toBeVisible({ timeout: 10000 });
    await publishBtn.click();
    const publishModal = page.getByRole("dialog");
    await expect(publishModal).toBeVisible({ timeout: 10000 });
    await expect(publishModal.getByRole("heading", { name: "Publish New Opportunity" })).toBeVisible({ timeout: 10000 });
    await page.screenshot({
      path: path.join(REFINEMENT_DIR, "desktop-composer.png"),
      fullPage: false,
    });
    await page.keyboard.press("Escape");
    await expect(publishModal).toBeHidden({ timeout: 10000 });

    // 1.4 Desktop Post Detail
    await page.goto("/posts/10000000-0000-0000-0000-000000000001", { waitUntil: "domcontentloaded", timeout: 10000 });
    const postHeading = page.getByRole("heading", { name: "Q3 Financial Services AI Risk Protocol Update" });
    await expect(postHeading).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("button", { name: "Explain Routing" })).toBeVisible({ timeout: 10000 });
    await page.screenshot({
      path: path.join(REFINEMENT_DIR, "desktop-post-detail.png"),
      fullPage: false,
    });

    // 1.5 Desktop Routing Explainability Drawer
    await page.getByRole("button", { name: "Explain Routing" }).click();
    const routingDrawer = page.getByRole("dialog");
    await expect(routingDrawer).toBeVisible({ timeout: 10000 });
    await expect(routingDrawer).toContainText("Semantic Routing Audit & Explainability", { timeout: 10000 });
    await expect(routingDrawer).toContainText("RiskGuard-Beta", { timeout: 10000 });
    await page.screenshot({
      path: path.join(REFINEMENT_DIR, "desktop-routing-drawer.png"),
      fullPage: false,
    });
    await page.keyboard.press("Escape");
    await expect(routingDrawer).toBeHidden({ timeout: 10000 });

    // ==========================================
    // 2. MOBILE VIEWPORT (390 x 844)
    // ==========================================

    // 2.1 Mobile Dashboard
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/dashboard", { waitUntil: "domcontentloaded", timeout: 10000 });
    await expect(page.getByRole("heading", { name: "Agent Workspace Dashboard" })).toBeVisible({ timeout: 10000 });
    await page.screenshot({
      path: path.join(REFINEMENT_DIR, "mobile-dashboard.png"),
      fullPage: false,
    });

    // 2.2 Mobile Feed
    await page.goto("/feed", { waitUntil: "domcontentloaded", timeout: 10000 });
    await expect(page.getByRole("heading", { name: "Opportunity Discovery Feed" })).toBeVisible({ timeout: 10000 });
    await expect(page.locator("[data-testid='post-card-10000000-0000-0000-0000-000000000001']")).toBeVisible({ timeout: 10000 });
    await page.screenshot({
      path: path.join(REFINEMENT_DIR, "mobile-feed.png"),
      fullPage: false,
    });

    // 2.3 Mobile Composer Modal
    const mobilePubBtn = page.getByRole("button", { name: "Publish Opportunity" });
    await expect(mobilePubBtn).toBeVisible({ timeout: 10000 });
    await mobilePubBtn.click();
    const mobileModal = page.getByRole("dialog");
    await expect(mobileModal).toBeVisible({ timeout: 10000 });
    await expect(mobileModal.getByRole("heading", { name: "Publish New Opportunity" })).toBeVisible({ timeout: 10000 });
    await page.screenshot({
      path: path.join(REFINEMENT_DIR, "mobile-composer.png"),
      fullPage: false,
    });
    await page.keyboard.press("Escape");
    await expect(mobileModal).toBeHidden({ timeout: 10000 });

    // 2.4 Mobile Post Detail
    await page.goto("/posts/10000000-0000-0000-0000-000000000001", { waitUntil: "domcontentloaded", timeout: 10000 });
    await expect(page.getByRole("heading", { name: "Q3 Financial Services AI Risk Protocol Update" })).toBeVisible({ timeout: 10000 });
    await page.screenshot({
      path: path.join(REFINEMENT_DIR, "mobile-post-detail.png"),
      fullPage: false,
    });
  });
});
