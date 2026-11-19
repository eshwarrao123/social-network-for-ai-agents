const path = require("node:path");
const fs = require("node:fs");
const http = require("node:http");
const cp = require("node:child_process");
const { chromium } = require("@playwright/test");

const ARTIFACTS_DIR = path.resolve(__dirname, "../../qa-artifacts/p923b");

async function waitForUrl(url, maxAttempts = 25, delayMs = 500) {
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
      console.log(`waitForUrl attempt ${i + 1} failed:`, err.message);
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }
  throw new Error(`Timeout waiting for ${url}`);
}

async function main() {
  if (!fs.existsSync(ARTIFACTS_DIR)) {
    fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
  }

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
    console.log("4. Authenticating via /connect...");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/connect", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("input[placeholder='asama_live_...']", { timeout: 5000 });
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard", { timeout: 8000 });
    await page.waitForTimeout(600);

    // 1. Desktop Feed (1440x900)
    console.log("5. Navigating to /feed and capturing Desktop Feed (1440x900)...");
    await page.goto("/feed", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("[data-testid^='post-card-']", { timeout: 6000 });
    await page.waitForTimeout(600); // Allow SWR render
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "desktop-feed.png") });

    // 2. Desktop Composer Modal (1440x900)
    console.log("6. Opening Broadcast Opportunity Modal and capturing Desktop Composer (1440x900)...");
    await page.getByRole("button", { name: "Broadcast Opportunity" }).click();
    await page.waitForSelector("#publish-dialog-title", { timeout: 5000 });
    await page.waitForTimeout(400); // transition
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "desktop-composer.png") });

    // Close modal
    await page.getByRole("button", { name: "Close dialog" }).click();
    await page.waitForTimeout(300);

    // 3. Desktop Post Detail (1440x900)
    console.log("7. Navigating to post detail and capturing Desktop Post Detail (1440x900)...");
    await page.goto("/posts/10000000-0000-0000-0000-000000000001", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("h1", { timeout: 6000 });
    await page.waitForSelector("[data-testid^='comment-card-']", { timeout: 6000 });
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "desktop-post-detail.png") });

    // 4. Mobile Feed (390x844)
    console.log("8. Switching to Mobile Viewport (390x844) and capturing Mobile Feed...");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/feed", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("[data-testid^='post-card-']", { timeout: 6000 });
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "mobile-feed.png") });

    // 5. Mobile Composer Modal (390x844)
    console.log("9. Opening Broadcast Opportunity Modal on Mobile and capturing Mobile Composer (390x844)...");
    await page.getByRole("button", { name: "Broadcast Opportunity" }).click();
    await page.waitForSelector("#publish-dialog-title", { timeout: 5000 });
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "mobile-composer.png") });

    // Close modal
    await page.getByRole("button", { name: "Close dialog" }).click();
    await page.waitForTimeout(300);

    // 6. Mobile Post Detail (390x844)
    console.log("10. Navigating to post detail on Mobile and capturing Mobile Post Detail (390x844)...");
    await page.goto("/posts/10000000-0000-0000-0000-000000000001", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("h1", { timeout: 6000 });
    await page.waitForSelector("[data-testid^='comment-card-']", { timeout: 6000 });
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "mobile-post-detail.png") });

    await browser.close();
    console.log("All P9.2.3B screenshots successfully captured!");
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
  console.error("Capture script failed:", err);
  process.exit(1);
});
