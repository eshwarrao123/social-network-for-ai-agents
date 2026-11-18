import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const ARTIFACTS_DIR = path.resolve(__dirname, "../../qa-artifacts/p923a");

test.describe("P9.2.3A Verdant Control Plane Visual Inspection QA", () => {
  test.beforeAll(async () => {
    if (!fs.existsSync(ARTIFACTS_DIR)) {
      fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
    }
  });

  test.beforeEach(async ({ request }) => {
    // Reset mock backend state
    await request.post("http://127.0.0.1:8000/__test_control/reset", { timeout: 10000 });
  });

  test("Capture P9.2.3A visual verification screenshots (Desktop & Mobile)", async ({ page }) => {
    // -------------------------------------------------------------
    // 1. Connect Page — Desktop (1440 x 900)
    // -------------------------------------------------------------
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/connect", { waitUntil: "domcontentloaded", timeout: 10000 });
    await expect(page.getByRole("heading", { name: "Agent Network" })).toBeVisible({ timeout: 10000 });
    const keyInput = page.locator("input[placeholder='asama_live_...']");
    await expect(keyInput).toBeVisible({ timeout: 10000 });

    await page.screenshot({
      path: path.join(ARTIFACTS_DIR, "connect-desktop-1440x900.png"),
      fullPage: false,
    });

    // -------------------------------------------------------------
    // 2. Connect Page — Mobile (390 x 844)
    // -------------------------------------------------------------
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/connect", { waitUntil: "domcontentloaded", timeout: 10000 });
    await expect(page.getByRole("heading", { name: "Agent Network" })).toBeVisible({ timeout: 10000 });

    await page.screenshot({
      path: path.join(ARTIFACTS_DIR, "connect-mobile-390x844.png"),
      fullPage: false,
    });

    // -------------------------------------------------------------
    // 3. Authenticate with deterministic test fixture key
    // -------------------------------------------------------------
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/connect", { waitUntil: "domcontentloaded", timeout: 10000 });
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard", { timeout: 10000 });

    // -------------------------------------------------------------
    // 4. Dashboard — Desktop (1440 x 900)
    // -------------------------------------------------------------
    const dashHeading = page.getByRole("heading", { name: "Agent Workspace Dashboard" });
    await expect(dashHeading).toBeVisible({ timeout: 10000 });
    await expect(page.locator("body")).toContainText("LiquidityBot-Alpha", { timeout: 10000 });
    await expect(page.locator("body")).toContainText("Apex Capital", { timeout: 10000 });

    await page.screenshot({
      path: path.join(ARTIFACTS_DIR, "dashboard-desktop-1440x900.png"),
      fullPage: false,
    });

    // -------------------------------------------------------------
    // 5. Desktop Sidebar Focus
    // -------------------------------------------------------------
    const sidebar = page.locator("aside");
    await expect(sidebar).toBeVisible({ timeout: 10000 });
    await sidebar.screenshot({
      path: path.join(ARTIFACTS_DIR, "desktop-sidebar.png"),
    });

    // -------------------------------------------------------------
    // 6. Dashboard — Mobile (390 x 844)
    // -------------------------------------------------------------
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/dashboard", { waitUntil: "domcontentloaded", timeout: 10000 });
    await expect(dashHeading).toBeVisible({ timeout: 10000 });
    await expect(page.locator("body")).toContainText("LiquidityBot-Alpha", { timeout: 10000 });

    await page.screenshot({
      path: path.join(ARTIFACTS_DIR, "dashboard-mobile-390x844.png"),
      fullPage: false,
    });

    // -------------------------------------------------------------
    // 7. Mobile Navigation Open
    // -------------------------------------------------------------
    const menuBtn = page.getByRole("button", { name: "Open navigation menu" });
    await expect(menuBtn).toBeVisible({ timeout: 10000 });
    await menuBtn.click();
    const mobileDrawer = page.locator("aside, div[aria-hidden='false']").filter({ hasText: "Control Plane" });
    await expect(mobileDrawer.first()).toBeVisible({ timeout: 10000 });

    await page.screenshot({
      path: path.join(ARTIFACTS_DIR, "mobile-nav-open.png"),
      fullPage: false,
    });
  });
});
