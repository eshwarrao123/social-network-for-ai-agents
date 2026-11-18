import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const QA_DIR = path.resolve(__dirname, "../../qa-artifacts/screenshots");

test.beforeAll(async () => {
  if (!fs.existsSync(QA_DIR)) {
    fs.mkdirSync(QA_DIR, { recursive: true });
  }
});

test.describe("Real Browser E2E Journeys & Security Audit", () => {
  test.beforeEach(async ({ request }) => {
    // Reset mock backend state
    await request.post("http://localhost:8000/__test_control/reset");
  });

  test("Journey A: Existing agent connection and dashboard transition", async ({
    page,
    context,
  }) => {
    // 1. Open /connect
    await page.goto("/connect");
    await expect(page).toHaveTitle(/Agent Network/);
    await expect(page.locator("h1")).toContainText("Agent Network");

    // Capture Desktop /connect screenshot
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.screenshot({ path: path.join(QA_DIR, "desktop-connect.png") });

    // 2. Enter valid API key for Agent A
    const apiKeyInput = page.locator("input[placeholder='asama_live_...']");
    await apiKeyInput.fill("asama_live_valid_agent_key_1");

    // 3. Submit
    await page.getByRole("button", { name: "Connect Workspace" }).click();

    // 4. Verify transition to /dashboard
    await page.waitForURL("**/dashboard", { timeout: 10000 });
    await expect(page.locator("h1")).toContainText("Agent Workspace Dashboard");

    // 5. Verify real agent profile values rendered from backend
    await expect(page.locator("body")).toContainText("LiquidityBot-Alpha");
    await expect(page.locator("body")).toContainText("Apex Capital");
    await expect(page.locator("body")).toContainText("95%"); // Trust score
    await expect(page.locator("body")).toContainText("asama_live_liqu"); // Prefix
    await expect(page.locator("body")).toContainText(
      "Autonomous high-throughput cross-currency liquidity agent"
    );

    // 6. Verify cookie presence and flags in browser context
    const cookies = await context.cookies();
    const sessionCookie = cookies.find((c) => c.name === "agent_session");
    expect(sessionCookie).toBeDefined();
    expect(sessionCookie?.httpOnly).toBe(true);
    expect(sessionCookie?.sameSite).toBe("Lax");
    expect(sessionCookie?.path).toBe("/");
    expect(sessionCookie?.value).toBe("jwt_token_agent_a");

    // Capture Desktop /dashboard screenshot
    await page.screenshot({ path: path.join(QA_DIR, "desktop-dashboard.png") });
  });

  test("Journey B: Invalid credentials handling", async ({ page, context }) => {
    await page.goto("/connect");

    // Submit invalid key
    const apiKeyInput = page.locator("input[placeholder='asama_live_...']");
    await apiKeyInput.fill("asama_live_invalid_unauthorized_key");
    await page.getByRole("button", { name: "Connect Workspace" }).click();

    // Verify accessible error alert appears
    const errorAlert = page.getByRole("alert").filter({ hasText: "Authentication Failed" });
    await expect(errorAlert).toBeVisible();
    await expect(errorAlert).toContainText("Authentication Failed");
    await expect(errorAlert).toContainText("Invalid or inactive agent API key");

    // Remain on /connect
    expect(page.url()).toContain("/connect");

    // Verify NO session cookie was set
    const cookies = await context.cookies();
    const sessionCookie = cookies.find((c) => c.name === "agent_session");
    expect(sessionCookie).toBeUndefined();
  });

  test("Journey C: Agent registration, one-time reveal modal, and state cleanup", async ({
    page,
  }) => {
    await page.goto("/connect");

    // Switch to Register tab
    await page.getByRole("tab", { name: "Register Enterprise Agent" }).click();

    // Fill registration form
    await page.locator("input[placeholder='e.g. RiskBot-Alpha']").fill("AlphaBot-New");
    await page
      .locator("input[placeholder='e.g. Meridian Capital']")
      .fill("AlphaGlobal Investments");
    await page
      .locator("textarea")
      .fill("Strategic high-frequency capital allocation and automated hedging.");
    await page
      .locator("input[placeholder='fintech, banking, risk-management']")
      .fill("fintech, asset-management");
    await page
      .locator("input[placeholder='market-analysis, compliance']")
      .fill("algorithmic-hedging");
    await page
      .locator("input[placeholder='equities, derivatives, fx']")
      .fill("hedging, macro");

    // Submit registration
    await page.getByRole("button", { name: "Register Agent & Generate Key" }).click();

    // Modal dialog must open
    const dialog = page.locator("[role='dialog']");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("Store Your Agent API Key");

    // Raw API key must be rendered
    const keyElement = dialog.locator("code");
    await expect(keyElement).toContainText("asama_live_registered_secret_key_9999");

    // Test Copy button
    const copyButton = dialog.getByRole("button", { name: "Copy" });
    await expect(copyButton).toBeVisible();
    await copyButton.click();
    await expect(dialog.getByRole("button", { name: "Copied" })).toBeVisible();

    // Checkbox is required before connecting or dismissing
    const connectNowBtn = dialog.getByRole("button", { name: "Connect Workspace Now" });
    expect(await connectNowBtn.isDisabled()).toBe(true);

    const checkbox = dialog.locator("input[type='checkbox']");
    await checkbox.check();
    expect(await connectNowBtn.isDisabled()).toBe(false);

    // Click Connect Workspace Now
    await connectNowBtn.click();

    // Should transition to dashboard
    await page.waitForURL("**/dashboard", { timeout: 10000 });

    // Verify key is NO LONGER in the rendered DOM anywhere
    const pageHtml = await page.content();
    expect(pageHtml).not.toContain("asama_live_registered_secret_key_9999");
  });

  test("Journey D: Session restoration, 401 expiration handling, and Disconnect", async ({
    page,
    context,
    request,
  }) => {
    // 1. Connect agent
    await page.goto("/connect");
    await page
      .locator("input[placeholder='asama_live_...']")
      .fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    // 2. Refresh page and verify session restoration
    await page.reload();
    await expect(page.locator("body")).toContainText("LiquidityBot-Alpha");
    await expect(page.locator("body")).toContainText("Apex Capital");

    // 3. Simulate backend 401 expiration
    await request.post("http://localhost:8000/__test_control/expire_session");

    // Trigger revalidation by querying session or reloading
    await page.reload();

    // Browser must detect expired session, clear cookie, and redirect to /connect?expired=true
    await page.waitForURL("**/connect?expired=true", { timeout: 10000 });
    const expiredAlert = page.getByRole("alert").filter({ hasText: "Session Expired" });
    await expect(expiredAlert).toBeVisible();
    await expect(expiredAlert).toContainText("Session Expired");

    // Verify cookie was cleared
    const cookiesAfterExpiry = await context.cookies();
    const expiredCookie = cookiesAfterExpiry.find((c) => c.name === "agent_session");
    expect(!expiredCookie || expiredCookie.value === "").toBe(true);

    // 4. Reconnect and test manual Disconnect button
    await request.post("http://localhost:8000/__test_control/reset");
    await page
      .locator("input[placeholder='asama_live_...']")
      .fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    // Click TopNav Disconnect button
    await page.getByRole("button", { name: "Disconnect" }).click();
    // Modal confirmation opens
    const disconnectDialog = page.locator("[role='dialog']");
    await expect(disconnectDialog).toBeVisible();
    await disconnectDialog.getByRole("button", { name: "Confirm Disconnect" }).click();

    // Must redirect to /connect
    await page.waitForURL("**/connect", { timeout: 10000 });
  });

  test("Journey E: Workspace navigation, disabled phases, and mobile responsiveness", async ({
    page,
  }) => {
    // Connect agent
    await page.goto("/connect");
    await page
      .locator("input[placeholder='asama_live_...']")
      .fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    // 1. Desktop navigation checks
    await page.setViewportSize({ width: 1280, height: 800 });
    const sidebar = page.locator("aside");
    await expect(sidebar).toBeVisible();
    // Verify enabled links
    await expect(sidebar.locator("a", { hasText: "Dashboard" })).toBeVisible();
    await expect(sidebar.locator("a", { hasText: "Opportunity Feed" })).toBeVisible();

    // Verify disabled future-phase nav items have P9.3 indicators and do not navigate
    const disabledInbox = sidebar.getByTitle("Inbound Inbox (Scheduled for P9.3)");
    await expect(disabledInbox).toBeVisible();
    await expect(disabledInbox).toContainText("P9.3");

    // 2. Mobile navigation checks (< 768px)
    await page.setViewportSize({ width: 375, height: 667 });

    // Sidebar should be hidden on mobile
    await expect(sidebar).toBeHidden();

    // Capture Mobile /dashboard screenshot
    await page.screenshot({ path: path.join(QA_DIR, "mobile-dashboard.png") });

    // Mobile bottom rail should be visible
    const mobileBottomNav = page.locator("nav[aria-label='Mobile Navigation']");
    await expect(mobileBottomNav).toBeVisible();

    // Mobile hamburger menu button in TopNav
    const hamburgerBtn = page.getByRole("button", { name: "Open navigation menu" });
    await expect(hamburgerBtn).toBeVisible();
    await hamburgerBtn.click();

    // Mobile drawer should slide in
    const mobileDrawer = page.locator("div.fixed.inset-y-0.left-0");
    await expect(mobileDrawer).toBeVisible();

    // Capture Mobile navigation open screenshot
    await page.screenshot({ path: path.join(QA_DIR, "mobile-nav-open.png") });

    // Close mobile drawer
    await page.getByRole("button", { name: "Close menu" }).click();
    await expect(mobileDrawer).toBeHidden();

    // Capture Mobile /connect screenshot
    await page.goto("/connect");
    await page.screenshot({ path: path.join(QA_DIR, "mobile-connect.png") });
  });

  test("Journey F: Tenant cache isolation across agent switching", async ({ page }) => {
    // 1. Connect Agent A
    await page.goto("/connect");
    await page
      .locator("input[placeholder='asama_live_...']")
      .fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    // Confirm Agent A is rendered
    await expect(page.locator("body")).toContainText("LiquidityBot-Alpha");
    await expect(page.locator("body")).toContainText("Apex Capital");
    expect(await page.content()).not.toContain("RiskGuard-Beta");

    // 2. Disconnect Agent A
    await page.getByRole("button", { name: "Disconnect" }).click();
    const disconnectDialog = page.locator("[role='dialog']");
    await disconnectDialog.getByRole("button", { name: "Confirm Disconnect" }).click();
    await page.waitForURL("**/connect");

    // 3. Connect Agent B in the same browser window
    await page
      .locator("input[placeholder='asama_live_...']")
      .fill("asama_live_valid_agent_key_2");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    // 4. Confirm Agent B is rendered
    await expect(page.locator("body")).toContainText("RiskGuard-Beta");
    await expect(page.locator("body")).toContainText("Meridian Partners");
    await expect(page.locator("body")).toContainText("88%");

    // 5. CRITICAL: Confirm Agent A's profile data NEVER leaked into Agent B's session
    const currentHtml = await page.content();
    expect(currentHtml).not.toContain("LiquidityBot-Alpha");
    expect(currentHtml).not.toContain("Apex Capital");
    expect(currentHtml).not.toContain("asama_live_liqu");
  });

  test("Journey G: Security audit in browser environment", async ({ page }) => {
    await page.goto("/connect");
    await page
      .locator("input[placeholder='asama_live_...']")
      .fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    // 1. Verify localStorage has NO tokens or secrets
    const localStorageData = await page.evaluate(() => {
      return {
        asama_token: localStorage.getItem("asama_token"),
        asama_agent: localStorage.getItem("asama_agent"),
        token: localStorage.getItem("token"),
        jwt: localStorage.getItem("jwt"),
        api_key: localStorage.getItem("api_key"),
        totalKeys: localStorage.length,
      };
    });
    expect(localStorageData.asama_token).toBeNull();
    expect(localStorageData.asama_agent).toBeNull();
    expect(localStorageData.token).toBeNull();
    expect(localStorageData.jwt).toBeNull();
    expect(localStorageData.api_key).toBeNull();

    // 2. Verify sessionStorage has NO tokens or secrets
    const sessionStorageLength = await page.evaluate(() => sessionStorage.length);
    expect(sessionStorageLength).toBe(0);

    // 3. Verify document.cookie CANNOT read the HttpOnly agent_session cookie
    const jsAccessibleCookies = await page.evaluate(() => document.cookie);
    expect(jsAccessibleCookies).not.toContain("agent_session");
    expect(jsAccessibleCookies).not.toContain("jwt_token");

    // 4. Verify protected API calls route strictly through same-origin BFF
    const bffCallResult = await page.evaluate(async () => {
      const res = await fetch("/api/v1/agents/me");
      return { status: res.status, ok: res.ok };
    });
    expect(bffCallResult.status).toBe(200);
    expect(bffCallResult.ok).toBe(true);
  });
});
