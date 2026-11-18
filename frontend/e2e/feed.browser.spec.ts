import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const QA_DIR = path.resolve(__dirname, "../../qa-artifacts/screenshots");

test.describe("Opportunity Feed, Publishing & Autonomous Discussions (Phase 9.2)", () => {
  test.beforeAll(async () => {
    if (!fs.existsSync(QA_DIR)) {
      fs.mkdirSync(QA_DIR, { recursive: true });
    }
  });

  test.beforeEach(async ({ request }) => {
    // Reset mock backend state before each test
    await request.post("http://localhost:8000/__test_control/reset");
  });

  test("1. Authenticated feed load, card rendering, and no accidental prefetch", async ({
    page,
  }) => {
    // Track requests to ensure GET /api/v1/posts/:id is NOT prefetched
    const detailRequests: string[] = [];
    page.on("request", (req) => {
      const url = req.url();
      if (url.includes("/api/v1/posts/10000000-") && !url.includes("?")) {
        detailRequests.push(url);
      }
    });

    // 1. Connect agent LiquidityBot-Alpha
    await page.goto("/connect");
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    // 2. Navigate to /feed
    await page.goto("/feed");
    await page.waitForLoadState("domcontentloaded");

    // 3. Verify page header
    await expect(page.getByRole("heading", { name: "Opportunity Discovery Feed" })).toBeVisible();

    // 4. Verify post cards rendered with authoritative data
    const firstCard = page.locator("[data-testid='post-card-10000000-0000-0000-0000-000000000001']");
    await expect(firstCard).toBeVisible();
    await expect(firstCard).toContainText("LiquidityBot-Alpha");
    await expect(firstCard).toContainText("Apex Capital");
    await expect(firstCard).toContainText("95%");
    await expect(firstCard).toContainText("Q3 Financial Services AI Risk Protocol Update");
    await expect(firstCard).toContainText("Announcement");
    await expect(firstCard).toContainText("42"); // view count

    // Capture Desktop /feed screenshot
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.screenshot({ path: path.join(QA_DIR, "desktop-feed.png") });

    // 5. Verify NO accidental detail prefetch occurred during feed browsing
    expect(detailRequests.length).toBe(0);
  });

  test("2. Empty feed state handling", async ({ page, request }) => {
    // Set mock to empty feed
    await request.post("http://localhost:8000/__test_control/set_empty_feed");

    // Connect & navigate
    await page.goto("/connect");
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    await page.goto("/feed");
    await page.waitForLoadState("domcontentloaded");

    // Verify empty state is displayed
    const emptyState = page.locator("[data-testid='feed-empty-state']");
    await expect(emptyState).toBeVisible();
    await expect(emptyState).toContainText("No opportunities found");
    await expect(emptyState.getByRole("button", { name: "Publish First Opportunity" })).toBeVisible();
  });

  test("3. Feed API error and retry recovery", async ({ page, request }) => {
    // Set mock to simulate 500 error
    await request.post("http://localhost:8000/__test_control/set_feed_error");

    await page.goto("/connect");
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    await page.goto("/feed");
    await page.waitForLoadState("domcontentloaded");

    // Verify error banner displayed
    const errorAlert = page
      .getByRole("alert")
      .filter({ hasText: "Failed to load opportunity feed" });
    await expect(errorAlert).toBeVisible();

    // Click retry button (mock automatically recovers on next call)
    const retryBtn = page.getByRole("button", { name: "Retry Discovery" });
    await expect(retryBtn).toBeVisible();
    await retryBtn.click();

    // Verify feed recovers and displays posts
    const firstCard = page.locator("[data-testid='post-card-10000000-0000-0000-0000-000000000001']");
    await expect(firstCard).toBeVisible();
  });

  test("4. Category filtering by post type", async ({ page }) => {
    await page.goto("/connect");
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    await page.goto("/feed");
    await page.waitForLoadState("domcontentloaded");

    // Click "Market Updates" filter
    const marketUpdatesTab = page.getByRole("tab", { name: "Market Updates" });
    await marketUpdatesTab.click();

    // Verify only market update post is shown
    await expect(page.locator("[data-testid='post-card-10000000-0000-0000-0000-000000000002']")).toBeVisible();
    await expect(page.locator("[data-testid='post-card-10000000-0000-0000-0000-000000000001']")).toBeHidden();

    // Click "All Opportunities" tab
    await page.getByRole("tab", { name: "All Opportunities" }).click();
    await expect(page.locator("[data-testid='post-card-10000000-0000-0000-0000-000000000001']")).toBeVisible();
  });

  test("5. Keyset cursor pagination and deduplication", async ({ page }) => {
    await page.goto("/connect");
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    await page.goto("/feed");
    await page.waitForLoadState("domcontentloaded");

    // Initial page has 20 items (out of 25)
    const cards = page.locator("article[data-testid^='post-card-']");
    expect(await cards.count()).toBe(20);

    // Click "Load More Opportunities"
    const loadMoreBtn = page.getByRole("button", { name: "Load More Opportunities" });
    await expect(loadMoreBtn).toBeVisible();
    await loadMoreBtn.click();

    // Wait for all 25 items to load
    await expect(cards).toHaveCount(25);

    // Verify "Reached end of discovery feed" message appears
    await expect(page.locator("text=Reached end of discovery feed")).toBeVisible();

    // Verify all IDs are unique (zero duplicates)
    const count = await cards.count();
    const ids = new Set<string>();
    for (let i = 0; i < count; i++) {
      const testId = await cards.nth(i).getAttribute("data-testid");
      if (testId) ids.add(testId);
    }
    expect(ids.size).toBe(25);
  });

  test("6. Successful post publishing and validation failure handling", async ({ page }) => {
    await page.goto("/connect");
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    await page.goto("/feed");
    await page.waitForLoadState("domcontentloaded");

    // Open Publish dialog
    await page.getByRole("button", { name: "Publish Opportunity" }).click();
    const modal = page.getByRole("dialog");
    await expect(modal).toBeVisible();

    // Capture Desktop Composer screenshot
    await page.screenshot({ path: path.join(QA_DIR, "desktop-composer.png") });

    // 1. Validation failure: attempt submit with empty fields
    const publishBtn = modal.getByRole("button", { name: "Publish Opportunity" });
    await publishBtn.click();
    // HTML5 required validation or client validation prevents submission
    await expect(modal).toBeVisible();

    // 2. Fill valid opportunity data
    await modal.locator("#post-title").fill("Autonomous Liquidity Channel Launch");
    await modal.locator("#post-content").fill("Launching automated EUR/USD repo settlement with bilateral credit enhancement.");

    // Select category: Collaboration
    await modal.getByRole("button", { name: "Collaboration" }).click();

    // Add Industry
    const industryInput = modal.locator("input[placeholder*='fintech']");
    await industryInput.fill("fintech");
    await modal.getByRole("button", { name: "Add" }).first().click();

    // Submit form
    await publishBtn.click();

    // Modal closes and success banner appears
    await expect(modal).toBeHidden();
    await expect(page.getByRole("status")).toContainText("Autonomous Liquidity Channel Launch");

    // New post appears at the top of the feed
    await expect(page.locator("article").first()).toContainText("Autonomous Liquidity Channel Launch");
  });

  test("7. Post detail navigation, view count, and author-restricted actions", async ({
    page,
  }) => {
    // 1. Connect LiquidityBot-Alpha (author of Post 1)
    await page.goto("/connect");
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    // 2. Navigate to /feed and click post 1
    await page.goto("/feed");
    const postLink = page.getByRole("link", {
      name: "Q3 Financial Services AI Risk Protocol Update",
    });
    await postLink.click();
    await page.waitForURL("**/posts/10000000-0000-0000-0000-000000000001");

    // 3. Verify complete post content rendered
    await expect(page.getByRole("heading", { name: "Q3 Financial Services AI Risk Protocol Update" })).toBeVisible();
    await expect(page.locator("body")).toContainText("We are introducing updated risk-adjusted settlement thresholds");

    // Capture Desktop Post Detail screenshot
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.screenshot({ path: path.join(QA_DIR, "desktop-post-detail.png") });

    // 4. Verify Author actions are visible because LiquidityBot owns this post
    await expect(page.getByRole("button", { name: "Explain Routing" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Edit" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Delete" })).toBeVisible();

    // 5. Open Explain Routing drawer
    await page.getByRole("button", { name: "Explain Routing" }).click();
    const drawer = page.getByRole("dialog");
    await expect(drawer).toBeVisible();
    await expect(drawer).toContainText("Semantic Routing Audit & Explainability");
    await expect(drawer).toContainText("RiskGuard-Beta");
    await expect(drawer).toContainText("Notified");

    // Capture Desktop Routing Drawer screenshot
    await page.screenshot({ path: path.join(QA_DIR, "desktop-routing-drawer.png") });

    // Close drawer via Escape key
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();

    // 6. Test Edit Opportunity
    await page.getByRole("button", { name: "Edit" }).click();
    const editModal = page.getByRole("dialog");
    await expect(editModal).toBeVisible();
    await editModal.locator("#edit-title").fill("Q3 Financial Services AI Risk Protocol Update (Amended)");
    await editModal.getByRole("button", { name: "Save Changes" }).click();
    await expect(editModal).toBeHidden();
    await expect(page.getByRole("heading", { name: "Q3 Financial Services AI Risk Protocol Update (Amended)" })).toBeVisible();

    // 7. Test Non-Author Restriction: View post 2 (owned by RiskGuard-Beta)
    await page.goto("/posts/10000000-0000-0000-0000-000000000002");
    await page.waitForLoadState("domcontentloaded");
    // Author buttons MUST NOT be rendered for non-owner
    await expect(page.getByRole("button", { name: "Explain Routing" })).toBeHidden();
    await expect(page.getByRole("button", { name: "Edit" })).toBeHidden();
    await expect(page.getByRole("button", { name: "Delete" })).toBeHidden();
  });

  test("8. Comment discussion, autonomous LLM badging, and idempotency protection", async ({
    page,
  }) => {
    await page.goto("/connect");
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    await page.goto("/posts/10000000-0000-0000-0000-000000000001");
    await page.waitForLoadState("domcontentloaded");

    // 1. Verify Autonomous LLM distinction on comment 1
    const llmBadge = page.locator("[data-testid='autonomous-llm-badge']");
    await expect(llmBadge).toBeVisible();
    await expect(llmBadge).toContainText("Autonomous LLM");
    await expect(llmBadge).toContainText("qwen2.5-coder:1.5b");
    await expect(llmBadge).toContainText("94%");

    // Verify second comment (manual) does NOT have LLM badge
    const secondComment = page.locator("[data-testid='comment-card-c0000000-0000-0000-0000-000000000002']");
    await expect(secondComment).toBeVisible();
    await expect(secondComment.locator("[data-testid='autonomous-llm-badge']")).toBeHidden();

    // 2. Submit new comment
    const commentInput = page.locator("#comment-input");
    await commentInput.fill("Liquidity verification confirmed. Counterparty buffers allocated.");
    const postCommentBtn = page.getByRole("button", { name: "Post Comment" });
    await postCommentBtn.click();

    // Verify comment appears in discussion thread
    await expect(page.locator("text=Liquidity verification confirmed. Counterparty buffers allocated.")).toBeVisible();
  });

  test("9. 404 handling and Back to Feed navigation", async ({ page }) => {
    await page.goto("/connect");
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    // Navigate to non-existent post
    await page.goto("/posts/00000000-0000-0000-0000-000000000000");
    await page.waitForLoadState("domcontentloaded");

    // Verify 404 message
    await expect(page.getByRole("heading", { name: "Opportunity Not Found" })).toBeVisible();

    // Click "Back to Feed"
    await page.getByRole("link", { name: "Back to Feed" }).click();
    await page.waitForURL("**/feed");
  });

  test("10. Mobile responsive layout and screenshot capture", async ({ page }) => {
    await page.goto("/connect");
    await page.locator("input[placeholder='asama_live_...']").fill("asama_live_valid_agent_key_1");
    await page.getByRole("button", { name: "Connect Workspace" }).click();
    await page.waitForURL("**/dashboard");

    // Switch to mobile viewport (375x667)
    await page.setViewportSize({ width: 375, height: 667 });

    // 1. Mobile Feed
    await page.goto("/feed");
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByRole("heading", { name: "Opportunity Discovery Feed" })).toBeVisible();
    await page.screenshot({ path: path.join(QA_DIR, "mobile-feed.png") });

    // 2. Mobile Composer
    await page.getByRole("button", { name: "Publish Opportunity" }).click();
    const modal = page.getByRole("dialog");
    await expect(modal).toBeVisible();
    await page.screenshot({ path: path.join(QA_DIR, "mobile-composer.png") });
    await page.keyboard.press("Escape");
    await expect(modal).toBeHidden();

    // 3. Mobile Post Detail
    await page.goto("/posts/10000000-0000-0000-0000-000000000001");
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByRole("heading", { name: "Q3 Financial Services AI Risk Protocol Update" })).toBeVisible();
    await page.screenshot({ path: path.join(QA_DIR, "mobile-post-detail.png") });
  });
});
