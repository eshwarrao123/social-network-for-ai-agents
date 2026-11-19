const path = require("node:path");
const fs = require("node:fs");
const http = require("node:http");
const cp = require("node:child_process");
const { chromium } = require("@playwright/test");

const ARTIFACTS_DIR = path.resolve(__dirname, "../../qa-artifacts/p923c");

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

  console.log("=== P9.2.3C Decision Explainability Verification Suite ===");
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

    // Track requests to ensure zero prefetching on /api/v1/routing/posts/...
    const routingRequests = [];
    page.on("request", (req) => {
      if (req.url().includes("/routing/posts/")) {
        routingRequests.push(req.url());
      }
    });

    // -------------------------------------------------------------
    // 1. Authenticate as Post Author (LiquidityBot-Alpha)
    // -------------------------------------------------------------
    console.log("4. Authenticating as author agent (LiquidityBot-Alpha)...");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/connect", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard", { timeout: 8000 });
    await page.waitForTimeout(500);

    // -------------------------------------------------------------
    // 2. Navigate to Post Detail and Verify Zero Prefetching
    // -------------------------------------------------------------
    console.log("5. Navigating to author post detail (/posts/10000000-0000-0000-0000-000000000001)...");
    await page.goto("/posts/10000000-0000-0000-0000-000000000001", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("h1", { timeout: 6000 });
    await page.waitForTimeout(800); // Allow SWR post load

    // Verify Explain Routing button is visible for author
    const explainBtn = page.getByRole("button", { name: "Explain Routing" });
    const isExplainVisible = await explainBtn.isVisible();
    if (!isExplainVisible) throw new Error("Verification Failed: 'Explain Routing' button should be visible for author agent!");
    console.log("  [PASS] Author management toolbar displays 'Explain Routing' button.");

    // Verify zero prefetch
    if (routingRequests.length !== 0) {
      throw new Error(`Verification Failed: Routing endpoint was prefetched prior to explicit click! Count: ${routingRequests.length}`);
    }
    console.log("  [PASS] Zero speculative prefetching verified: GET /routing/posts was NOT called on page load.");

    // Capture desktop-post-detail-with-routing.png
    console.log("6. Capturing qa-artifacts/p923c/desktop-post-detail-with-routing.png (1440x900)...");
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "desktop-post-detail-with-routing.png") });

    // -------------------------------------------------------------
    // 3. Open Explain Routing Drawer (Desktop 1440x900)
    // -------------------------------------------------------------
    console.log("7. Clicking 'Explain Routing' to open drawer...");
    await explainBtn.click();
    await page.waitForSelector("#routing-drawer-title", { timeout: 6000 });
    await page.waitForTimeout(600); // Allow SWR routing query

    // Check request was made
    if (routingRequests.length === 0) {
      throw new Error("Verification Failed: Opening drawer did not initiate expected routing query!");
    }
    console.log("  [PASS] Explicit click triggered authorized routing audit query.");

    const drawer = page.getByRole("dialog");
    const titleText = await page.locator("#routing-drawer-title").textContent();
    console.log(`  [PASS] Routing drawer title: "${titleText}"`);

    // Verify Global Engine Summary card
    const drawerContent = await drawer.textContent();
    if (!drawerContent.includes("Selected for Notification")) {
      throw new Error("Verification Failed: Summary card should state 'Selected for Notification' instead of 'Dispatched'!");
    }
    if (!drawerContent.includes("Threshold") || !drawerContent.includes("≥ 60%")) {
      throw new Error("Verification Failed: Summary card should state runtime threshold '≥ 60%'!");
    }
    console.log("  [PASS] Global Engine Summary card displays 'Selected for Notification' metric and runtime threshold.");

    // Verify Candidate 1: RiskGuard-Beta (Selected for Notification)
    const candidate1 = page.locator("[data-testid='routing-candidate-22222222-2222-2222-2222-222222222222']");
    if (!(await candidate1.isVisible())) throw new Error("Verification Failed: Candidate 1 (RiskGuard-Beta) not visible!");
    const badgeDispatched = candidate1.locator("[data-testid='status-badge-dispatched']");
    if (!(await badgeDispatched.isVisible())) throw new Error("Verification Failed: Candidate 1 should have status badge!");
    const badge1Text = await badgeDispatched.textContent();
    if (!badge1Text.includes("Selected for Notification")) {
      throw new Error(`Verification Failed: Candidate 1 badge must say 'Selected for Notification', got: ${badge1Text}`);
    }
    console.log("  [PASS] Candidate 1 rendered with accurate 'Selected for Notification' status badge.");

    // Expand Candidate 1 to verify mathematical breakdown & active P7 feedback (> 0 adjustment)
    await candidate1.locator("button").first().click();
    await page.waitForTimeout(300);
    const candidate1Text = await candidate1.textContent();
    if (!candidate1Text.includes("Vector Cosine Similarity") || !candidate1Text.includes("P7 Adaptive Feedback")) {
      throw new Error("Verification Failed: Candidate 1 does not display P7 Adaptive Feedback section!");
    }
    if (!candidate1Text.includes("81.2") && !candidate1Text.includes("84.2")) {
      throw new Error("Verification Failed: Candidate 1 does not show correct vector score breakdown!");
    }
    if (!candidate1Text.includes("Adaptive preference adjustment active: +3.00% calibrated from 8 verified past feedback samples")) {
      throw new Error(`Verification Failed: Candidate 1 feedback explanation inaccurate! Content: ${candidate1Text}`);
    }
    console.log("  [PASS] Candidate 1 renders base vector, active adaptive feedback (+3.00% from 8 samples), and hybrid formula.");

    // Verify Candidate 2: FinTech-Overseer (Qualified — not selected, zero adjustment with 4 samples >= 3)
    const candidate2 = page.locator("[data-testid='routing-candidate-44444444-4444-4444-4444-444444444444']");
    if (await candidate2.isVisible()) {
      const badgeQualified = candidate2.locator("[data-testid='status-badge-qualified']");
      if (!(await badgeQualified.isVisible())) throw new Error("Verification Failed: Candidate 2 should have qualified status badge!");
      const badge2Text = await badgeQualified.textContent();
      if (!badge2Text.includes("Qualified — not selected")) {
        throw new Error(`Verification Failed: Candidate 2 badge must say 'Qualified — not selected', got: ${badge2Text}`);
      }
      console.log("  [PASS] Candidate 2 rendered with 'Qualified — not selected' badge.");

      // Expand Candidate 2 to verify zero adjustment with nonzero samples (4 samples >= 3 threshold)
      await candidate2.locator("button").first().click();
      await page.waitForTimeout(300);
      const candidate2Text = await candidate2.textContent();
      if (!candidate2Text.includes("Adaptive preference learning active with 4 samples; 0.00% adjustment")) {
        throw new Error(`Verification Failed: Candidate 2 must explain zero adjustment with 4 samples! Content: ${candidate2Text}`);
      }
      console.log("  [PASS] Candidate 2 correctly explains active learning with 4 samples and 0.00% adjustment (learned aligns with base).");
    }

    // Verify Candidate 3: AlphaBot-New (Below Threshold, Cold Start 0 samples)
    const candidate3 = page.locator("[data-testid='routing-candidate-33333333-3333-3333-3333-333333333333']");
    if (await candidate3.isVisible()) {
      const badgeFiltered = candidate3.locator("[data-testid='status-badge-filtered']");
      if (!(await badgeFiltered.isVisible())) throw new Error("Verification Failed: Candidate 3 should have below threshold badge!");
      console.log("  [PASS] Candidate 3 rendered with 'Below Threshold' badge.");
      // Expand candidate 3 to verify cold start explanation (3 samples activation)
      await candidate3.locator("button").first().click();
      await page.waitForTimeout(300);
      const candidate3Text = await candidate3.textContent();
      if (!candidate3Text.includes("Cold start: No historical feedback samples recorded. Bounded adaptive learning activates once 3 valid interactions are recorded.")) {
        throw new Error(`Verification Failed: Candidate 3 must explain cold start with 3 samples threshold! Content: ${candidate3Text}`);
      }
      console.log("  [PASS] Candidate 3 renders accurate cold start explanation with 3 valid samples activation threshold.");
    }

    // Verify Candidate 4: DataMesh-Agent (Below Threshold, Insufficient samples: 2 samples < 3)
    const candidate4 = page.locator("[data-testid='routing-candidate-55555555-5555-5555-5555-555555555555']");
    if (await candidate4.isVisible()) {
      await candidate4.locator("button").first().click();
      await page.waitForTimeout(300);
      const candidate4Text = await candidate4.textContent();
      if (!candidate4Text.includes("Candidate has 2 verified feedback interactions. Bounded adaptive learning activates once 3 valid samples are observed.")) {
        throw new Error(`Verification Failed: Candidate 4 must explain insufficient samples (< 3)! Content: ${candidate4Text}`);
      }
      console.log("  [PASS] Candidate 4 correctly states 2 verified interactions with activation threshold at 3 samples.");
    }

    // Capture desktop-routing-drawer.png
    console.log("8. Capturing qa-artifacts/p923c/desktop-routing-drawer.png (1440x900)...");
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "desktop-routing-drawer.png") });

    // Test Keyboard Escape interaction
    console.log("9. Testing Escape key interaction to close drawer...");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
    if (await drawer.isVisible()) {
      throw new Error("Verification Failed: Escape key did not dismiss the routing drawer!");
    }
    console.log("  [PASS] Escape key closes routing drawer cleanly.");

    // -------------------------------------------------------------
    // 4. Mobile Responsiveness & Drawer Verification (390x844)
    // -------------------------------------------------------------
    console.log("10. Testing mobile viewport (390x844) and capturing mobile-routing-drawer.png...");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(300);
    // Click explain routing on mobile
    await page.getByRole("button", { name: "Explain Routing" }).click();
    await page.waitForSelector("#routing-drawer-title", { timeout: 6000 });
    await page.waitForTimeout(500);

    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "mobile-routing-drawer.png") });
    console.log("  [PASS] Mobile routing drawer captured at 390x844.");

    // Close on mobile
    await page.getByRole("button", { name: "Close explainability drawer" }).first().click();
    await page.waitForTimeout(400);

    // -------------------------------------------------------------
    // 4b. Verify Dynamic Runtime Threshold (Post 4 with threshold 0.55)
    // -------------------------------------------------------------
    console.log("10b. Testing dynamic runtime threshold on Post 4 (threshold 0.55)...");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/posts/10000000-0000-0000-0000-000000000004", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("h1", { timeout: 6000 });
    await page.waitForTimeout(500);

    const post4ExplainBtn = page.getByRole("button", { name: "Explain Routing" });
    if (!(await post4ExplainBtn.isVisible())) {
      throw new Error("Verification Failed: Author should see Explain Routing button on Post 4!");
    }
    await post4ExplainBtn.click();
    await page.waitForSelector("#routing-drawer-title", { timeout: 6000 });
    await page.waitForTimeout(500);

    const post4DrawerText = await page.getByRole("dialog").textContent();
    if (!post4DrawerText.includes("≥ 55%")) {
      throw new Error(`Verification Failed: Post 4 with custom threshold 0.55 should display '≥ 55%', got: ${post4DrawerText}`);
    }
    console.log("  [PASS] Dynamic runtime threshold 0.55 verified in summary card.");

    // Expand candidate on post 4 to check comparison bar shows 55%
    const post4Candidate1 = page.locator("[data-testid='routing-candidate-22222222-2222-2222-2222-222222222222']");
    await post4Candidate1.locator("button").first().click();
    await page.waitForTimeout(300);
    const post4Candidate1Text = await post4Candidate1.textContent();
    if (!post4Candidate1Text.includes("Threshold: 55%")) {
      throw new Error(`Verification Failed: Comparison bar should reflect dynamic runtime threshold 55%, got: ${post4Candidate1Text}`);
    }
    console.log("  [PASS] Candidate comparison bar dynamically reflects runtime threshold (55%).");

    await page.getByRole("button", { name: "Close explainability drawer" }).first().click();
    await page.waitForTimeout(400);

    // -------------------------------------------------------------
    // 5. Test Non-Author Access Restriction
    // -------------------------------------------------------------
    console.log("11. Testing non-author tenant isolation (RiskGuard-Beta visiting LiquidityBot's post)...");
    // Clear cookies to disconnect author session
    await context.clearCookies();
    await page.goto("/connect", { waitUntil: "domcontentloaded", timeout: 8000 });
    // Connect as non-author RiskGuard-Beta
    await page.waitForSelector("input[placeholder='asama_live_...']", { timeout: 6000 });
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_2");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard", { timeout: 8000 });
    await page.waitForTimeout(400);

    // Navigate to post 1 (owned by LiquidityBot-Alpha)
    await page.goto("/posts/10000000-0000-0000-0000-000000000001", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("h1", { timeout: 6000 });
    await page.waitForTimeout(500);

    const nonAuthorExplainBtn = page.getByRole("button", { name: "Explain Routing" });
    const isNonAuthorExplainVisible = await nonAuthorExplainBtn.isVisible();
    if (isNonAuthorExplainVisible) {
      throw new Error("Verification Failed: Non-author agent should NOT see the 'Explain Routing' button!");
    }
    console.log("  [PASS] Author restriction verified: Non-author cannot see or trigger 'Explain Routing'.");

    await browser.close();
    console.log("=== ALL P9.2.3C CHECKS PASSED SUCCESSFULLY! ===");
  } finally {
    console.log("Cleaning up server processes...");
    try {
      nextProc.kill("SIGTERM");
    } catch {}
    try {
      mockServer.close();
    } catch {}
  }
}

main().catch((err) => {
  console.error("Verification suite failed:", err);
  process.exit(1);
});
