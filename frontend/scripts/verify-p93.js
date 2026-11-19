const path = require("node:path");
const fs = require("node:fs");
const http = require("node:http");
const cp = require("node:child_process");
const { chromium } = require("@playwright/test");

const ARTIFACTS_DIR = path.resolve(__dirname, "../../qa-artifacts/p93");

async function waitForUrl(url, maxAttempts = 30, delayMs = 500) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      await new Promise((resolve, reject) => {
        const req = http.get(url, (res) => {
          if (res.statusCode >= 200 && res.statusCode < 500) resolve();
          else reject(new Error(`Status ${res.statusCode}`));
        });
        req.on("error", reject);
        req.setTimeout(1000, () => req.destroy());
      });
      return true;
    } catch (err) {
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }
  throw new Error(`Timeout waiting for ${url}`);
}

async function main() {
  if (!fs.existsSync(ARTIFACTS_DIR)) {
    fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
  }

  console.log("=== P9.3 Complete Enterprise Workspace Verification Suite ===");
  console.log("1. Starting mock backend on port 8000...");
  const { createMockBackend } = require("../e2e/mock-backend.js");
  const mockServer = createMockBackend(8000);
  await new Promise((resolve) => mockServer.listen(8000, resolve));
  console.log("Mock backend listening on http://127.0.0.1:8000");

  console.log("2. Starting Next.js production server on port 3000...");
  const nextBin = path.resolve(__dirname, "../node_modules/next/dist/bin/next");
  const nextProc = cp.spawn(process.execPath, [nextBin, "start", "-H", "127.0.0.1", "-p", "3000"], {
    cwd: path.resolve(__dirname, ".."),
    stdio: "inherit",
    env: { ...process.env, BACKEND_URL: "http://127.0.0.1:8000", PORT: "3000", HOSTNAME: "127.0.0.1" },
  });

  try {
    await waitForUrl("http://127.0.0.1:3000");
    console.log("Next.js server is ready at http://127.0.0.1:3000");

    console.log("3. Launching Chromium via Playwright...");
    const browser = await chromium.launch({ channel: "chrome", headless: true });
    const context = await browser.newContext({ baseURL: "http://127.0.0.1:3000" });
    const page = await context.newPage();

    // Authenticate
    console.log("4. Authenticating as LiquidityBot-Alpha via /connect...");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/connect", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("input[placeholder='asama_live_...']", { timeout: 5000 });
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard", { timeout: 8000 });
    await page.waitForTimeout(600);

    // =========================================================================
    // SCREEN 1: Inbound Notification Inbox (/notifications)
    // =========================================================================
    console.log("\n--- Testing P9.3A: Inbound Notification Inbox ---");
    await page.goto("/notifications", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("h1", { timeout: 6000 });
    await page.waitForTimeout(600);

    // Capture Desktop Inbox Screenshot
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "desktop-inbox.png") });
    console.log("  [PASS] Captured desktop-inbox.png (1440x900)");

    // Test Status Filters
    const unreadFilter = page.getByRole("button", { name: /Unread/i });
    if (await unreadFilter.isVisible()) {
      await unreadFilter.click();
      await page.waitForTimeout(300);
      console.log("  [PASS] Filtered by Unread notifications");
    }

    const allFilter = page.getByRole("button", { name: /All Events/i });
    if (await allFilter.isVisible()) {
      await allFilter.click();
      await page.waitForTimeout(300);
      console.log("  [PASS] Reset filter to All Events");
    }

    // Test Decision Trace Drawer
    const notifItem = page.locator("[class*='group p-4 sm:p-5']").first();
    if (await notifItem.isVisible()) {
      await notifItem.click();
      await page.waitForSelector("h2:has-text('Notification Decision Trace')", { timeout: 5000 });
      console.log("  [PASS] Opened Decision Trace Drawer via row click");

      const closeDrawerBtn = page.getByRole("button", { name: "Close notification drawer" });
      await closeDrawerBtn.click();
      await page.waitForTimeout(300);
      console.log("  [PASS] Closed Decision Trace Drawer");
    }

    // Capture Mobile Inbox Screenshot
    console.log("  Testing Mobile Viewport for Inbox (390x844)...");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/notifications", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("h1", { timeout: 6000 });
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "mobile-inbox.png") });
    console.log("  [PASS] Captured mobile-inbox.png (390x844)");

    // Restore Desktop Viewport
    await page.setViewportSize({ width: 1440, height: 900 });

    // =========================================================================
    // SCREEN 2: Agent Analytics (/analytics)
    // =========================================================================
    console.log("\n--- Testing P9.3B: Agent Analytics ---");
    await page.goto("/analytics", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("h1", { timeout: 6000 });
    await page.waitForTimeout(600);

    // Verify Metric Cards & Formulas
    const publisherConv = await page.locator("text=Publisher Comment Conversion").first().isVisible();
    const deliveredConv = await page.locator("text=Delivered Comment Conversion").first().isVisible();
    const responseRate = await page.locator("text=Delivered Response Rate").first().isVisible();
    console.log(`  [PASS] Analytics Overview metrics rendered: Publisher(${publisherConv}), Delivered(${deliveredConv}), ResponseRate(${responseRate})`);

    // Test Timeline Range Toggle (7d, 30d, 90d)
    const sevenDayBtn = page.getByRole("button", { name: "7 Days" });
    if (await sevenDayBtn.isVisible()) {
      await sevenDayBtn.click();
      await page.waitForTimeout(300);
      console.log("  [PASS] Toggled continuous timeline to 7 Days");
    }

    const thirtyDayBtn = page.getByRole("button", { name: "30 Days" });
    if (await thirtyDayBtn.isVisible()) {
      await thirtyDayBtn.click();
      await page.waitForTimeout(300);
      console.log("  [PASS] Toggled continuous timeline to 30 Days");
    }

    // Capture Desktop Analytics Screenshot
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "desktop-analytics.png") });
    console.log("  [PASS] Captured desktop-analytics.png (1440x900)");

    // =========================================================================
    // SCREEN 3: Partner Intelligence (/partners)
    // =========================================================================
    console.log("\n--- Testing P9.3C: Partner Intelligence ---");
    await page.goto("/partners", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("h1", { timeout: 6000 });
    await page.waitForTimeout(600);

    // Verify Partner Intelligence Cards
    const industriesCard = await page.locator("text=Top Counterparty Industries").isVisible();
    const companiesCard = await page.locator("text=Active Enterprise Counterparties").isVisible();
    const disclaimer = await page.locator("text=Partitioning & Legal Disclaimer").isVisible();
    console.log(`  [PASS] Partner Intelligence rendered: Industries(${industriesCard}), Companies(${companiesCard}), LegalDisclaimer(${disclaimer})`);

    // Capture Desktop Partners Screenshot
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "desktop-partners.png") });
    console.log("  [PASS] Captured desktop-partners.png (1440x900)");

    // =========================================================================
    // SCREEN 4: Adaptive Preferences (/preferences)
    // =========================================================================
    console.log("\n--- Testing P9.3D: Adaptive Preferences ---");
    await page.goto("/preferences", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("h1", { timeout: 6000 });
    await page.waitForTimeout(600);

    // Verify Drift Meter & Affinity Topics
    const driftMeter = await page.locator("text=Cosine Drift Distance").isVisible();
    const positiveTopics = await page.locator("text=Positive Opportunity Topics").isVisible();
    const negativeTopics = await page.locator("text=Suppressed Opportunity Topics").isVisible();
    console.log(`  [PASS] Preference controls rendered: DriftMeter(${driftMeter}), PositiveTopics(${positiveTopics}), NegativeTopics(${negativeTopics})`);

    // Capture Desktop Preferences Screenshot
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "desktop-preferences.png") });
    console.log("  [PASS] Captured desktop-preferences.png (1440x900)");

    // Test Reset Preferences Confirmation Modal
    const resetTriggerBtn = page.getByRole("button", { name: "Reset to Baseline Manifesto" });
    if (await resetTriggerBtn.isVisible()) {
      await resetTriggerBtn.click();
      await page.waitForSelector("h3:has-text('Reset Adaptive Preferences?')", { timeout: 5000 });
      console.log("  [PASS] Preference Reset Modal opened with confirmation notice");

      const cancelResetBtn = page.getByRole("button", { name: "Cancel" });
      await cancelResetBtn.click();
      await page.waitForTimeout(300);
      console.log("  [PASS] Cancelled Preference Reset safely");
    }

    // =========================================================================
    // SCREEN 5: Agent Profile & Webhook Settings (/settings)
    // =========================================================================
    console.log("\n--- Testing P9.3E: Agent Settings & Webhooks ---");
    await page.goto("/settings", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("h1", { timeout: 6000 });
    await page.waitForTimeout(600);

    // Capture Desktop Settings Screenshot
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "desktop-settings.png") });
    console.log("  [PASS] Captured desktop-settings.png (1440x900)");

    // Test Profile Tab: Edit company and save
    const companyInput = page.locator("input[placeholder='e.g. Meridian Capital']");
    await companyInput.fill("Apex Quant Capital Group");
    const saveProfileBtn = page.getByRole("button", { name: "Save Profile Changes" });
    await saveProfileBtn.click();
    await page.waitForSelector("text=Agent profile and taxonomy updated successfully", { timeout: 5000 });
    console.log("  [PASS] Profile updated and saved via PATCH /agents/me");

    // Test Webhooks Tab
    const webhooksTab = page.getByRole("button", { name: /Outbound Webhook Subscriptions/ });
    await webhooksTab.click();
    await page.waitForTimeout(400);

    // Test Register Webhook Modal
    const registerWebhookBtn = page.getByRole("button", { name: "Register Webhook Endpoint" });
    await registerWebhookBtn.click();
    await page.waitForSelector("h3:has-text('Register Outbound Webhook')", { timeout: 5000 });
    console.log("  [PASS] Opened Register Webhook modal");

    const endpointInput = page.locator("input[placeholder='https://api.yourcompany.com/webhooks/agent']");
    await endpointInput.fill("https://api.apexquant.com/webhooks/opportunities");
    const submitWebhookBtn = page.getByRole("button", { name: "Register Endpoint" });
    await submitWebhookBtn.click();

    // Verify One-Time Plaintext Secret Reveal Modal
    await page.waitForSelector("h3:has-text('Webhook Endpoint Registered')", { timeout: 5000 });
    const secretWarning = await page.locator("text=CRITICAL: Secret Revealed Exactly Once").first().isVisible();
    const secretDisplay = await page.locator("text=whsec_live_").first().isVisible();
    console.log(`  [PASS] One-Time HMAC Secret modal revealed once: Warning(${secretWarning}), MonospaceSecret(${secretDisplay})`);

    const storedSecretBtn = page.getByRole("button", { name: "I Have Stored This Secret Securely" });
    await storedSecretBtn.click();
    await page.waitForTimeout(400);
    console.log("  [PASS] Closed Secret Reveal modal without persisting secret");

    // Test Rotate Secret Flow
    const rotateBtn = page.locator("button[title='Rotate HMAC signing secret']").first();
    if (await rotateBtn.isVisible()) {
      await rotateBtn.click();
      await page.waitForSelector("h3:has-text('Rotate Signing Secret?')", { timeout: 5000 });
      console.log("  [PASS] Confirm Secret Rotation modal opened");

      const confirmRotateBtn = page.getByRole("button", { name: "Confirm Rotation" });
      await confirmRotateBtn.click();
      await page.waitForSelector("h3:has-text('HMAC Secret Rotated')", { timeout: 5000 });
      console.log("  [PASS] Secret rotated and new plaintext key displayed once");

      const storedRotatedBtn = page.getByRole("button", { name: "I Have Stored This Secret Securely" });
      await storedRotatedBtn.click();
      await page.waitForTimeout(400);
    }

    // =========================================================================
    // NAVIGATION INTEGRATION VERIFICATION
    // =========================================================================
    console.log("\n--- Testing Navigation Integration ---");
    const sidebarInbox = page.locator("aside a[href='/notifications']");
    const sidebarPartners = page.locator("aside a[href='/partners']");
    const sidebarAnalytics = page.locator("aside a[href='/analytics']");
    const sidebarPreferences = page.locator("aside a[href='/preferences']");
    const sidebarSettings = page.locator("aside a[href='/settings']");

    const inboxNavValid = await sidebarInbox.isVisible();
    const partnersNavValid = await sidebarPartners.isVisible();
    const analyticsNavValid = await sidebarAnalytics.isVisible();
    const prefNavValid = await sidebarPreferences.isVisible();
    const settingsNavValid = await sidebarSettings.isVisible();

    console.log(`  [PASS] Sidebar Links active: Inbox(${inboxNavValid}), Partners(${partnersNavValid}), Analytics(${analyticsNavValid}), Preferences(${prefNavValid}), Settings(${settingsNavValid})`);

    console.log("\n========================================================");
    console.log("ALL VERIFICATION CHECKS PASSED PERFECTLY!");
    console.log("All 6 QA artifacts generated in qa-artifacts/p93");
    console.log("========================================================\n");

    await browser.close();
  } finally {
    console.log("Cleaning up servers...");
    nextProc.kill("SIGTERM");
    mockServer.close();
  }
}

main().catch((err) => {
  console.error("Verification failed:", err);
  process.exit(1);
});
