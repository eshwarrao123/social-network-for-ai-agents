const path = require("node:path");
const fs = require("node:fs");
const http = require("node:http");
const cp = require("node:child_process");
const { chromium } = require("@playwright/test");

const ARTIFACTS_DIR = path.resolve(__dirname, "../../qa-artifacts/p923a");

async function waitForUrl(url, maxAttempts = 20, delayMs = 500) {
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

    console.log("3. Launching Chrome via Playwright...");
    const browser = await chromium.launch({ channel: "chrome", headless: true });
    const context = await browser.newContext({ baseURL: "http://127.0.0.1:3000" });
    const page = await context.newPage();

    // 1. Desktop Connect (1440x900)
    console.log("4. Capturing Desktop Connect (1440x900)...");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/connect", { waitUntil: "domcontentloaded", timeout: 8000 });
    await page.waitForSelector("h1", { timeout: 5000 });
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "desktop-connect.png") });

    // 2. Mobile Connect (390x844)
    console.log("5. Capturing Mobile Connect (390x844)...");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "mobile-connect.png") });

    // 3. Authenticate
    console.log("6. Authenticating via /connect...");
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard", { timeout: 8000 });
    await page.waitForSelector("h1", { timeout: 5000 });

    // 4. Desktop Dashboard (1440x900)
    console.log("7. Capturing Desktop Dashboard (1440x900)...");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.waitForTimeout(1000); // Allow SWR to hydrate profile
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "desktop-dashboard.png") });

    // 4b. Desktop Sidebar Focus
    console.log("7b. Capturing Desktop Sidebar...");
    const sidebar = page.locator("aside");
    if (await sidebar.isVisible()) {
      await sidebar.screenshot({ path: path.join(ARTIFACTS_DIR, "desktop-sidebar.png") });
    }

    // 5. Mobile Dashboard (390x844)
    console.log("8. Capturing Mobile Dashboard (390x844)...");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, "mobile-dashboard.png") });

    // 6. Mobile Navigation Open (390x844)
    console.log("9. Opening Mobile Navigation and Capturing...");
    const menuBtn = page.getByRole("button", { name: "Open navigation menu" });
    if (await menuBtn.isVisible()) {
      await menuBtn.click();
      await page.waitForTimeout(400); // transition
      await page.screenshot({ path: path.join(ARTIFACTS_DIR, "mobile-nav-open.png") });
    }

    await browser.close();
    console.log("Screenshot capture successfully completed!");
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
  console.error("Capture failed:", err);
  process.exit(1);
});
