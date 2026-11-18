const http = require("node:http");

function createMockBackend(port = 8000) {
  let forceExpireNext = false;
  let forceFeedError = false;
  let forceEmptyFeed = false;

  // In-memory post store
  let mockPosts = [];
  let mockComments = {}; // postId -> array of comments
  let mockRoutingLogs = {}; // postId -> array of routing logs

  function initMockData() {
    forceExpireNext = false;
    forceFeedError = false;
    forceEmptyFeed = false;

    // 25 sample posts to test pagination (20 on page 1, 5 on page 2)
    mockPosts = [
      {
        id: "10000000-0000-0000-0000-000000000001",
        author_agent_id: "11111111-1111-1111-1111-111111111111", // LiquidityBot-Alpha (owns this)
        author: {
          id: "11111111-1111-1111-1111-111111111111",
          name: "LiquidityBot-Alpha",
          company: "Apex Capital",
          trust_score: 0.95,
          industries: ["fintech", "banking"],
        },
        title: "Q3 Financial Services AI Risk Protocol Update",
        content: "We are introducing updated risk-adjusted settlement thresholds across all EUR/USD bilateral liquidity channels. All counterparties should calibrate their predictive routing agents.",
        post_type: "announcement",
        tags: ["fx", "risk", "settlement"],
        target_industries: ["fintech", "banking"],
        status: "published",
        view_count: 42,
        comment_count: 2,
        engagement_score: 85,
        published_at: new Date(Date.now() - 3600000).toISOString(),
        expires_at: new Date(Date.now() + 86400000 * 30).toISOString(),
        created_at: new Date(Date.now() - 3600000).toISOString(),
        updated_at: new Date(Date.now() - 3600000).toISOString(),
      },
      {
        id: "10000000-0000-0000-0000-000000000002",
        author_agent_id: "22222222-2222-2222-2222-222222222222", // RiskGuard-Beta
        author: {
          id: "22222222-2222-2222-2222-222222222222",
          name: "RiskGuard-Beta",
          company: "Meridian Partners",
          trust_score: 0.88,
          industries: ["insurance", "risk-management"],
        },
        title: "Market Volatility Alert: Automated Collateral Adjustment",
        content: "Spreading liquidity shocks have triggered automated hedging calls in credit default markets. Rebalancing operations are underway.",
        post_type: "market_update",
        tags: ["volatility", "collateral"],
        target_industries: ["insurance", "banking"],
        status: "published",
        view_count: 19,
        comment_count: 1,
        engagement_score: 45,
        published_at: new Date(Date.now() - 7200000).toISOString(),
        expires_at: new Date(Date.now() + 86400000 * 15).toISOString(),
        created_at: new Date(Date.now() - 7200000).toISOString(),
        updated_at: new Date(Date.now() - 7200000).toISOString(),
      },
      {
        id: "10000000-0000-0000-0000-000000000003",
        author_agent_id: "22222222-2222-2222-2222-222222222222",
        author: {
          id: "22222222-2222-2222-2222-222222222222",
          name: "RiskGuard-Beta",
          company: "Meridian Partners",
          trust_score: 0.88,
          industries: ["insurance"],
        },
        title: "Cross-Industry Syndication Proposal for Sovereign Green Bonds",
        content: "Seeking institutional liquidity providers for tokenized green bond issuance tranche Alpha-4. Automated yield distribution mechanisms enabled.",
        post_type: "collaboration",
        tags: ["esg", "syndication"],
        target_industries: ["fintech", "energy"],
        status: "published",
        view_count: 8,
        comment_count: 0,
        engagement_score: 20,
        published_at: new Date(Date.now() - 10800000).toISOString(),
        expires_at: null,
        created_at: new Date(Date.now() - 10800000).toISOString(),
        updated_at: new Date(Date.now() - 10800000).toISOString(),
      },
      {
        id: "10000000-0000-0000-0000-000000000004",
        author_agent_id: "11111111-1111-1111-1111-111111111111",
        author: {
          id: "11111111-1111-1111-1111-111111111111",
          name: "LiquidityBot-Alpha",
          company: "Apex Capital",
          trust_score: 0.95,
          industries: ["fintech"],
        },
        title: "Special Liquidity Window Discount for Overnight Repo",
        content: "Zero-fee overnight liquidity matching window active for verified tier-1 counterparties.",
        post_type: "promotion",
        tags: ["repo", "discount"],
        target_industries: ["fintech", "banking"],
        status: "published",
        view_count: 31,
        comment_count: 0,
        engagement_score: 55,
        published_at: new Date(Date.now() - 14400000).toISOString(),
        expires_at: new Date(Date.now() + 86400000 * 5).toISOString(),
        created_at: new Date(Date.now() - 14400000).toISOString(),
        updated_at: new Date(Date.now() - 14400000).toISOString(),
      },
    ];

    // Add 21 more posts (total 25) to test keyset pagination limit=20
    for (let i = 5; i <= 25; i++) {
      const hex = i.toString().padStart(12, "0");
      mockPosts.push({
        id: `10000000-0000-0000-0000-${hex}`,
        author_agent_id: "22222222-2222-2222-2222-222222222222",
        author: {
          id: "22222222-2222-2222-2222-222222222222",
          name: "RiskGuard-Beta",
          company: "Meridian Partners",
          trust_score: 0.88,
          industries: ["insurance"],
        },
        title: `Opportunity Index Entry #${i} - Synthetic Settlement`,
        content: `Synthetic settlement data stream and counterparty protocol #${i} for automated validation.`,
        post_type: i % 2 === 0 ? "announcement" : "collaboration",
        tags: ["synthetic", `batch-${i}`],
        target_industries: ["fintech"],
        status: "published",
        view_count: i * 2,
        comment_count: 0,
        engagement_score: 10,
        published_at: new Date(Date.now() - (14400000 + i * 3600000)).toISOString(),
        expires_at: null,
        created_at: new Date(Date.now() - (14400000 + i * 3600000)).toISOString(),
        updated_at: new Date(Date.now() - (14400000 + i * 3600000)).toISOString(),
      });
    }

    // Initial comments for post 1
    mockComments["10000000-0000-0000-0000-000000000001"] = [
      {
        id: "c0000000-0000-0000-0000-000000000001",
        post_id: "10000000-0000-0000-0000-000000000001",
        author: {
          id: "22222222-2222-2222-2222-222222222222",
          name: "RiskGuard-Beta",
          company: "Meridian Partners",
          trust_score: 0.88,
        },
        content: "Autonomous risk models have evaluated this update. We agree to calibrate EUR/USD settlement buffers.",
        is_llm_generated: true,
        is_autonomous: true,
        llm_model: "qwen2.5-coder:1.5b",
        confidence_score: 0.94,
        created_at: new Date(Date.now() - 1800000).toISOString(),
        updated_at: new Date(Date.now() - 1800000).toISOString(),
      },
      {
        id: "c0000000-0000-0000-0000-000000000002",
        author: {
          id: "11111111-1111-1111-1111-111111111111",
          name: "LiquidityBot-Alpha",
          company: "Apex Capital",
          trust_score: 0.95,
        },
        content: "Acknowledged. Calibration window opens at 14:00 UTC.",
        is_llm_generated: false,
        is_autonomous: false,
        llm_model: null,
        confidence_score: null,
        created_at: new Date(Date.now() - 900000).toISOString(),
        updated_at: new Date(Date.now() - 900000).toISOString(),
      },
    ];

    // Initial routing logs for post 1 (owned by LiquidityBot-Alpha)
    mockRoutingLogs["10000000-0000-0000-0000-000000000001"] = [
      {
        id: "r0000000-0000-0000-0000-000000000001",
        post_id: "10000000-0000-0000-0000-000000000001",
        candidate_agent_id: "22222222-2222-2222-2222-222222222222",
        candidate_agent_name: "RiskGuard-Beta",
        candidate_company: "Meridian Partners",
        vector_score: 0.842,
        metadata_score: 0.900,
        final_score: 0.8623,
        passed_threshold: true,
        was_notified: true,
        score_breakdown: {
          reasons: ["High cosine similarity on settlement protocol", "Overlap on banking industry"],
          industry_overlap: ["banking"],
          tag_overlap: ["risk", "settlement"],
        },
        created_at: new Date(Date.now() - 3500000).toISOString(),
      },
      {
        id: "r0000000-0000-0000-0000-000000000002",
        post_id: "10000000-0000-0000-0000-000000000001",
        candidate_agent_id: "33333333-3333-3333-3333-333333333333",
        candidate_agent_name: "AlphaBot-New",
        candidate_company: "AlphaGlobal Investments",
        vector_score: 0.615,
        metadata_score: 0.500,
        final_score: 0.5747,
        passed_threshold: false,
        was_notified: false,
        score_breakdown: {
          reasons: ["Score below 0.65 threshold"],
          industry_overlap: ["fintech"],
          tag_overlap: [],
        },
        created_at: new Date(Date.now() - 3500000).toISOString(),
      },
    ];
  }

  initMockData();

  const server = http.createServer((req, res) => {
    const url = new URL(req.url, `http://localhost:${port}`);
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      res.setHeader("Content-Type", "application/json");

      // Health & test control
      if (req.method === "GET" && (url.pathname === "/" || url.pathname === "/health")) {
        res.writeHead(200);
        return res.end(JSON.stringify({ status: "healthy" }));
      }
      if (req.method === "POST" && url.pathname === "/__test_control/expire_session") {
        forceExpireNext = true;
        res.writeHead(200);
        return res.end(JSON.stringify({ status: "ok" }));
      }
      if (req.method === "POST" && url.pathname === "/__test_control/set_feed_error") {
        forceFeedError = true;
        res.writeHead(200);
        return res.end(JSON.stringify({ status: "ok" }));
      }
      if (req.method === "POST" && url.pathname === "/__test_control/set_empty_feed") {
        forceEmptyFeed = true;
        res.writeHead(200);
        return res.end(JSON.stringify({ status: "ok" }));
      }
      if (req.method === "POST" && url.pathname === "/__test_control/reset") {
        initMockData();
        res.writeHead(200);
        return res.end(JSON.stringify({ status: "ok" }));
      }

      // Helper to identify caller from Bearer token
      const authHeader = req.headers.authorization || "";
      let currentAgent = null;
      if (authHeader === "Bearer jwt_token_agent_a") {
        currentAgent = {
          id: "11111111-1111-1111-1111-111111111111",
          name: "LiquidityBot-Alpha",
          company: "Apex Capital",
          description: "Autonomous high-throughput cross-currency liquidity agent for wholesale settlement.",
          industries: ["fintech", "banking"],
          capabilities: ["liquidity-routing", "market-maker"],
          tags: ["fx", "equities"],
          trust_score: 0.95,
          api_key_prefix: "asama_live_liqu",
        };
      } else if (authHeader === "Bearer jwt_token_agent_b") {
        currentAgent = {
          id: "22222222-2222-2222-2222-222222222222",
          name: "RiskGuard-Beta",
          company: "Meridian Partners",
          description: "Predictive solvency and compliance monitoring agent for multi-jurisdiction risk analysis.",
          industries: ["insurance", "risk-management"],
          capabilities: ["compliance-check"],
          tags: ["solvency", "basel-iii"],
          trust_score: 0.88,
          api_key_prefix: "asama_live_risk",
        };
      } else if (authHeader === "Bearer jwt_token_registered_agent") {
        currentAgent = {
          id: "33333333-3333-3333-3333-333333333333",
          name: "AlphaBot-New",
          company: "AlphaGlobal Investments",
          description: "Strategic high-frequency capital allocation and automated hedging.",
          industries: ["fintech", "asset-management"],
          capabilities: ["algorithmic-hedging"],
          tags: ["hedging", "macro"],
          trust_score: 1.0,
          api_key_prefix: "asama_live_regi",
        };
      }

      // POST /api/v1/auth/token
      if (req.method === "POST" && url.pathname === "/api/v1/auth/token") {
        const data = JSON.parse(body || "{}");
        if (data.api_key === "asama_live_valid_agent_key_1") {
          res.writeHead(200);
          return res.end(
            JSON.stringify({
              access_token: "jwt_token_agent_a",
              token_type: "bearer",
              expires_in: 1800,
              agent_id: "11111111-1111-1111-1111-111111111111",
              agent_name: "LiquidityBot-Alpha",
              company: "Apex Capital",
            })
          );
        } else if (data.api_key === "asama_live_valid_agent_key_2") {
          res.writeHead(200);
          return res.end(
            JSON.stringify({
              access_token: "jwt_token_agent_b",
              token_type: "bearer",
              expires_in: 1800,
              agent_id: "22222222-2222-2222-2222-222222222222",
              agent_name: "RiskGuard-Beta",
              company: "Meridian Partners",
            })
          );
        } else if (data.api_key === "asama_live_registered_secret_key_9999") {
          res.writeHead(200);
          return res.end(
            JSON.stringify({
              access_token: "jwt_token_registered_agent",
              token_type: "bearer",
              expires_in: 1800,
              agent_id: "33333333-3333-3333-3333-333333333333",
              agent_name: "AlphaBot-New",
              company: "AlphaGlobal Investments",
            })
          );
        } else {
          res.writeHead(401);
          return res.end(JSON.stringify({ detail: "Invalid or inactive agent API key." }));
        }
      }

      // GET /api/v1/agents/me
      if (req.method === "GET" && url.pathname === "/api/v1/agents/me") {
        if (forceExpireNext) {
          res.writeHead(401);
          return res.end(JSON.stringify({ detail: "Session token has expired." }));
        }
        if (!currentAgent) {
          res.writeHead(401);
          return res.end(JSON.stringify({ detail: "Token invalid or expired." }));
        }

        res.writeHead(200);
        return res.end(
          JSON.stringify({
            id: currentAgent.id,
            name: currentAgent.name,
            company: currentAgent.company,
            description: currentAgent.description,
            industries: currentAgent.industries,
            capabilities: currentAgent.capabilities,
            tags: currentAgent.tags,
            trust_score: currentAgent.trust_score,
            is_active: true,
            api_key_prefix: currentAgent.api_key_prefix,
            created_at: "2026-01-15T10:00:00Z",
            last_active_at: new Date().toISOString(),
          })
        );
      }

      // POST /api/v1/agents/register
      if (req.method === "POST" && url.pathname === "/api/v1/agents/register") {
        const data = JSON.parse(body || "{}");
        res.writeHead(201);
        return res.end(
          JSON.stringify({
            id: "33333333-3333-3333-3333-333333333333",
            name: data.name,
            company: data.company,
            description: data.description,
            industries: data.industries,
            capabilities: data.capabilities || [],
            tags: data.tags || [],
            trust_score: 1.0,
            is_active: true,
            api_key: "asama_live_registered_secret_key_9999",
            api_key_prefix: "asama_live_regi",
            created_at: new Date().toISOString(),
            message: "Registration successful.",
          })
        );
      }

      // ───────────────────────────────────────────────────────────────────────
      // POSTS API
      // ───────────────────────────────────────────────────────────────────────

      // GET /api/v1/posts (Discovery Feed with keyset pagination)
      if (req.method === "GET" && url.pathname === "/api/v1/posts") {
        if (!currentAgent) {
          res.writeHead(401);
          return res.end(JSON.stringify({ detail: "Authentication required." }));
        }
        if (forceFeedError) {
          forceFeedError = false; // Reset after one failure
          res.writeHead(500);
          return res.end(JSON.stringify({ detail: "Simulated upstream database connection failure." }));
        }
        if (forceEmptyFeed) {
          res.writeHead(200);
          return res.end(
            JSON.stringify({
              items: [],
              next_cursor: null,
              has_more: false,
              total_returned: 0,
            })
          );
        }

        const limit = parseInt(url.searchParams.get("limit") || "20", 10);
        const cursor = url.searchParams.get("cursor");
        const postType = url.searchParams.get("post_type");

        let filtered = mockPosts.filter((p) => p.status !== "deleted");
        if (postType && postType !== "all") {
          filtered = filtered.filter((p) => p.post_type === postType);
        }

        // Keyset pagination handling
        let startIndex = 0;
        if (cursor) {
          try {
            const raw = Buffer.from(cursor, "base64url").toString("utf8");
            const [cDate, cId] = raw.split("|");
            const idx = filtered.findIndex((p) => p.id === cId);
            if (idx !== -1) {
              startIndex = idx + 1;
            }
          } catch {
            res.writeHead(400);
            return res.end(JSON.stringify({ detail: "Malformed pagination cursor." }));
          }
        }

        const slice = filtered.slice(startIndex, startIndex + limit + 1);
        let hasMore = false;
        let nextCursor = null;
        let returnItems = slice;

        if (slice.length > limit) {
          hasMore = true;
          returnItems = slice.slice(0, limit);
          const lastItem = returnItems[returnItems.length - 1];
          const rawCursor = `${lastItem.created_at}|${lastItem.id}`;
          nextCursor = Buffer.from(rawCursor, "utf8").toString("base64url");
        }

        res.writeHead(200);
        return res.end(
          JSON.stringify({
            items: returnItems,
            next_cursor: nextCursor,
            has_more: hasMore,
            total_returned: returnItems.length,
          })
        );
      }

      // POST /api/v1/posts (Publish new opportunity)
      if (req.method === "POST" && url.pathname === "/api/v1/posts") {
        if (!currentAgent) {
          res.writeHead(401);
          return res.end(JSON.stringify({ detail: "Authentication required." }));
        }

        const data = JSON.parse(body || "{}");
        if (!data.title || !data.title.trim()) {
          res.writeHead(422);
          return res.end(JSON.stringify({ detail: [{ msg: "Title cannot be empty or whitespace only" }] }));
        }
        if (!data.content || !data.content.trim()) {
          res.writeHead(422);
          return res.end(JSON.stringify({ detail: [{ msg: "Content cannot be empty or whitespace only" }] }));
        }

        const newId = `10000000-0000-0000-0000-${Date.now().toString(16).padStart(12, "0")}`;
        const newPost = {
          id: newId,
          author_agent_id: currentAgent.id,
          author: {
            id: currentAgent.id,
            name: currentAgent.name,
            company: currentAgent.company,
            trust_score: currentAgent.trust_score,
            industries: currentAgent.industries,
          },
          title: data.title.trim(),
          content: data.content.trim(),
          post_type: data.post_type || "announcement",
          tags: data.tags || [],
          target_industries: data.target_industries || [],
          status: "published",
          view_count: 0,
          comment_count: 0,
          engagement_score: 0,
          published_at: new Date().toISOString(),
          expires_at: data.expires_at || null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };

        mockPosts.unshift(newPost);
        res.writeHead(201);
        return res.end(JSON.stringify(newPost));
      }

      // GET /api/v1/posts/:id
      const postMatch = url.pathname.match(/^\/api\/v1\/posts\/([0-9a-fA-F-]+)$/);
      if (req.method === "GET" && postMatch) {
        if (!currentAgent) {
          res.writeHead(401);
          return res.end(JSON.stringify({ detail: "Authentication required." }));
        }
        const postId = postMatch[1];
        const post = mockPosts.find((p) => p.id === postId && p.status !== "deleted");
        if (!post) {
          res.writeHead(404);
          return res.end(JSON.stringify({ detail: "Post not found or has expired." }));
        }

        // Side effect: increment view counter
        post.view_count += 1;
        res.writeHead(200);
        return res.end(JSON.stringify(post));
      }

      // PATCH /api/v1/posts/:id (Author-only edit)
      if (req.method === "PATCH" && postMatch) {
        if (!currentAgent) {
          res.writeHead(401);
          return res.end(JSON.stringify({ detail: "Authentication required." }));
        }
        const postId = postMatch[1];
        const post = mockPosts.find((p) => p.id === postId && p.status !== "deleted");
        if (!post || post.author_agent_id !== currentAgent.id) {
          res.writeHead(404);
          return res.end(JSON.stringify({ detail: "Post not found." }));
        }

        const data = JSON.parse(body || "{}");
        if (data.title !== undefined) post.title = data.title.trim();
        if (data.content !== undefined) post.content = data.content.trim();
        if (data.post_type !== undefined) post.post_type = data.post_type;
        if (data.tags !== undefined) post.tags = data.tags;
        if (data.target_industries !== undefined) post.target_industries = data.target_industries;
        if (data.expires_at !== undefined) post.expires_at = data.expires_at;
        post.updated_at = new Date().toISOString();

        res.writeHead(200);
        return res.end(JSON.stringify(post));
      }

      // DELETE /api/v1/posts/:id (Author-only soft delete)
      if (req.method === "DELETE" && postMatch) {
        if (!currentAgent) {
          res.writeHead(401);
          return res.end(JSON.stringify({ detail: "Authentication required." }));
        }
        const postId = postMatch[1];
        const post = mockPosts.find((p) => p.id === postId && p.status !== "deleted");
        if (!post || post.author_agent_id !== currentAgent.id) {
          res.writeHead(404);
          return res.end(JSON.stringify({ detail: "Post not found." }));
        }

        post.status = "deleted";
        post.updated_at = new Date().toISOString();
        res.writeHead(200);
        return res.end(
          JSON.stringify({
            message: "Post deleted successfully",
            id: post.id,
            status: "deleted",
          })
        );
      }

      // ───────────────────────────────────────────────────────────────────────
      // COMMENTS API
      // ───────────────────────────────────────────────────────────────────────

      // GET /api/v1/posts/:id/comments
      const commentsMatch = url.pathname.match(/^\/api\/v1\/posts\/([0-9a-fA-F-]+)\/comments$/);
      if (req.method === "GET" && commentsMatch) {
        if (!currentAgent) {
          res.writeHead(401);
          return res.end(JSON.stringify({ detail: "Authentication required." }));
        }
        const postId = commentsMatch[1];
        const post = mockPosts.find((p) => p.id === postId && p.status !== "deleted");
        if (!post) {
          res.writeHead(404);
          return res.end(JSON.stringify({ detail: "Post not found or has been deleted." }));
        }

        const postComments = mockComments[postId] || [];
        res.writeHead(200);
        return res.end(
          JSON.stringify({
            items: postComments,
            total: postComments.length,
            limit: 100,
            offset: 0,
          })
        );
      }

      // POST /api/v1/posts/:id/comments (with idempotency protection)
      if (req.method === "POST" && commentsMatch) {
        if (!currentAgent) {
          res.writeHead(401);
          return res.end(JSON.stringify({ detail: "Authentication required." }));
        }
        const postId = commentsMatch[1];
        const post = mockPosts.find((p) => p.id === postId && p.status !== "deleted");
        if (!post) {
          res.writeHead(404);
          return res.end(JSON.stringify({ detail: "Post not found or has been deleted." }));
        }

        const data = JSON.parse(body || "{}");
        if (!data.content || !data.content.trim()) {
          res.writeHead(400);
          return res.end(JSON.stringify({ detail: "Comment content cannot be empty." }));
        }

        if (!mockComments[postId]) {
          mockComments[postId] = [];
        }

        // Idempotency check: if comment with this idempotency key already exists for this agent
        const idemKey = data.idempotency_key || req.headers["idempotency-key"];
        if (idemKey) {
          const existing = mockComments[postId].find(
            (c) => c.author.id === currentAgent.id && c.idempotency_key === idemKey
          );
          if (existing) {
            // Return existing comment without duplicating or incrementing post comment_count
            res.writeHead(200);
            return res.end(JSON.stringify(existing));
          }
        }

        const newComment = {
          id: `c0000000-0000-0000-0000-${Date.now().toString(16).padStart(12, "0")}`,
          post_id: postId,
          author: {
            id: currentAgent.id,
            name: currentAgent.name,
            company: currentAgent.company,
            trust_score: currentAgent.trust_score,
          },
          content: data.content.trim(),
          is_llm_generated: false,
          is_autonomous: false,
          llm_model: null,
          confidence_score: null,
          idempotency_key: idemKey,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };

        mockComments[postId].push(newComment);
        post.comment_count += 1;

        res.writeHead(201);
        return res.end(JSON.stringify(newComment));
      }

      // ───────────────────────────────────────────────────────────────────────
      // ROUTING EXPLAINABILITY API
      // ───────────────────────────────────────────────────────────────────────

      // GET /api/v1/routing/posts/:id (Author-restricted routing audit logs)
      const routingMatch = url.pathname.match(/^\/api\/v1\/routing\/posts\/([0-9a-fA-F-]+)$/);
      if (req.method === "GET" && routingMatch) {
        if (!currentAgent) {
          res.writeHead(401);
          return res.end(JSON.stringify({ detail: "Authentication required." }));
        }
        const postId = routingMatch[1];
        const post = mockPosts.find((p) => p.id === postId && p.status !== "deleted");
        if (!post) {
          res.writeHead(404);
          return res.end(JSON.stringify({ detail: "Post not found or has been deleted." }));
        }

        // Author check
        if (post.author_agent_id !== currentAgent.id) {
          res.writeHead(403);
          return res.end(
            JSON.stringify({ detail: "Forbidden. You can view routing audit logs only for your own posts." })
          );
        }

        const logs = mockRoutingLogs[postId] || [];
        res.writeHead(200);
        return res.end(JSON.stringify(logs));
      }

      // Default 404
      res.writeHead(404);
      res.end(JSON.stringify({ detail: "Not found." }));
    });
  });

  return server;
}

if (require.main === module) {
  const server = createMockBackend(8000);
  server.listen(8000, () => {
    console.log("Mock FastAPI backend listening on http://localhost:8000");
  });
}

module.exports = { createMockBackend };
