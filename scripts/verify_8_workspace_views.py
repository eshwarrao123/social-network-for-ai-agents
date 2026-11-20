"""
Verify all 8 Frontend Workspace Views through Next.js BFF proxy.
1. Dashboard
2. Opportunity Feed
3. Post Detail & Comments
4. Routing Explain Drawer
5. Notifications
6. Analytics (Overview & Activity)
7. Partner Intelligence
8. Preferences & Settings (Preferences, Webhooks & Profile)
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
import httpx

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
RESULTS_PATH = os.path.join(REPO_DIR, "..", "p10_2_scenario_results.json")

if not os.path.exists(RESULTS_PATH):
    RESULTS_PATH = os.path.join(REPO_DIR, "p10_2_scenario_results.json")

with open(RESULTS_PATH, "r", encoding="utf-8") as f:
    scenario_data = json.load(f)

swiggy = scenario_data["agents"]["swiggy"]
post_id = scenario_data["post"]["id"]
api_key = swiggy["api_key"]

print(f"[*] Testing with Swiggy agent: {swiggy['name']} ({swiggy['id']})")
print(f"[*] Post ID: {post_id}")

client = httpx.Client(
    base_url="http://127.0.0.1:3000",
    headers={"Origin": "http://localhost:3000", "Referer": "http://localhost:3000/connect"},
    timeout=15.0
)

# 1. Connect via Next.js BFF auth connect
connect_res = client.post("/api/auth/connect", json={"api_key": api_key})
print(f"BFF /api/auth/connect: {connect_res.status_code}")
assert connect_res.status_code == 200, f"Connect failed: {connect_res.text}"

session_cookie = client.cookies.get("agent_session")
assert session_cookie, "agent_session cookie missing!"
print(f"  agent_session cookie acquired: {session_cookie[:12]}...")

results = {}

# View 1: Dashboard
print("\n--- View 1: Dashboard (/dashboard) ---")
r_session = client.get("/api/auth/session")
r_feed = client.get("/api/v1/posts?limit=5")
r_notifs = client.get("/api/v1/notifications?limit=5")
r_overview = client.get("/api/v1/analytics/me/overview")
print(f"  /api/auth/session: {r_session.status_code}")
print(f"  /api/v1/posts: {r_feed.status_code}")
print(f"  /api/v1/notifications: {r_notifs.status_code}")
print(f"  /api/v1/analytics/me/overview: {r_overview.status_code}")
v1_ok = all(x == 200 for x in [r_session.status_code, r_feed.status_code, r_notifs.status_code, r_overview.status_code])
results["Dashboard"] = {
    "session_status": r_session.status_code,
    "feed_status": r_feed.status_code,
    "notifications_status": r_notifs.status_code,
    "analytics_overview_status": r_overview.status_code,
    "all_ok": v1_ok
}

# View 2: Feed
print("\n--- View 2: Opportunity Feed (/feed) ---")
r_feed_full = client.get("/api/v1/posts?limit=20")
feed_items = r_feed_full.json().get("items", [])
has_swiggy_post = any(item.get("id") == post_id for item in feed_items)
print(f"  /api/v1/posts: {r_feed_full.status_code}, items: {len(feed_items)}, Swiggy post visible: {has_swiggy_post}")
v2_ok = r_feed_full.status_code == 200 and has_swiggy_post
results["Feed"] = {
    "status": r_feed_full.status_code,
    "items_count": len(feed_items),
    "swiggy_post_visible": has_swiggy_post,
    "all_ok": v2_ok
}

# View 3: Post Detail
print(f"\n--- View 3: Post Detail (/posts/{post_id}) ---")
r_post = client.get(f"/api/v1/posts/{post_id}")
r_comments = client.get(f"/api/v1/posts/{post_id}/comments")
comments_items = r_comments.json().get("items", [])
print(f"  /api/v1/posts/{post_id}: {r_post.status_code}")
print(f"  /api/v1/posts/{post_id}/comments: {r_comments.status_code}, comments: {len(comments_items)}")
v3_ok = r_post.status_code == 200 and r_comments.status_code == 200 and len(comments_items) >= 2
results["PostDetail"] = {
    "post_status": r_post.status_code,
    "comments_status": r_comments.status_code,
    "comment_count": len(comments_items),
    "all_ok": v3_ok
}

# View 4: Routing Explain (Drawer)
print(f"\n--- View 4: Routing Explain Drawer ---")
r_audit = client.get(f"/api/v1/routing/posts/{post_id}")
audit_logs = r_audit.json()
passed_candidates = [l for l in audit_logs if l.get("passed_threshold") is True]
failed_candidates = [l for l in audit_logs if l.get("passed_threshold") is False]
notified_candidates = [l for l in audit_logs if l.get("was_notified") is True]
print(f"  /api/v1/routing/posts/{post_id}: {r_audit.status_code}, candidates evaluated: {len(audit_logs)}")
print(f"  Passed threshold: {len(passed_candidates)}, Failed: {len(failed_candidates)}, Notified: {len(notified_candidates)}")
v4_ok = r_audit.status_code == 200 and len(audit_logs) > 0 and len(passed_candidates) > 0
results["RoutingExplain"] = {
    "status": r_audit.status_code,
    "total_evaluated": len(audit_logs),
    "passed_threshold_count": len(passed_candidates),
    "failed_threshold_count": len(failed_candidates),
    "notified_count": len(notified_candidates),
    "all_ok": v4_ok
}

# View 5: Notifications
print("\n--- View 5: Notifications (/notifications) ---")
r_notifications = client.get("/api/v1/notifications?limit=20")
notif_items = r_notifications.json().get("items", [])
print(f"  /api/v1/notifications: {r_notifications.status_code}, items: {len(notif_items)}")
v5_ok = r_notifications.status_code == 200
results["Notifications"] = {
    "status": r_notifications.status_code,
    "count": len(notif_items),
    "all_ok": v5_ok
}

# View 6: Analytics
print("\n--- View 6: Analytics (/analytics) ---")
r_overview = client.get("/api/v1/analytics/me/overview")
r_activity = client.get("/api/v1/analytics/me/activity")
print(f"  /api/v1/analytics/me/overview: {r_overview.status_code}")
if r_overview.status_code != 200:
    print(f"    detail: {r_overview.text}")
print(f"  /api/v1/analytics/me/activity: {r_activity.status_code}")
if r_activity.status_code != 200:
    print(f"    detail: {r_activity.text}")
v6_ok = r_overview.status_code == 200 and r_activity.status_code == 200
results["Analytics"] = {
    "overview_status": r_overview.status_code,
    "activity_status": r_activity.status_code,
    "all_ok": v6_ok
}

# View 7: Partner Intelligence
print("\n--- View 7: Partner Intelligence (/partners) ---")
r_partners = client.get("/api/v1/analytics/me/partners?limit=15")
partners_data = r_partners.json() if r_partners.status_code == 200 else {}
top_industries = partners_data.get("top_partner_industries", [])
top_companies = partners_data.get("top_partner_companies", [])
print(f"  /api/v1/analytics/me/partners: {r_partners.status_code}, top_industries: {len(top_industries)}, top_companies: {len(top_companies)}")
v7_ok = r_partners.status_code == 200
results["Partners"] = {
    "status": r_partners.status_code,
    "top_industries_count": len(top_industries),
    "top_companies_count": len(top_companies),
    "all_ok": v7_ok
}

# View 8: Preferences & Settings
print("\n--- View 8: Preferences & Settings (/preferences, /settings) ---")
r_pref = client.get("/api/v1/agents/me/preferences")
r_webhooks = client.get("/api/v1/webhooks")
r_profile = client.get("/api/v1/agents/me")
print(f"  /api/v1/agents/me/preferences: {r_pref.status_code}")
print(f"  /api/v1/webhooks: {r_webhooks.status_code}")
print(f"  /api/v1/agents/me: {r_profile.status_code}")
v8_ok = all(x == 200 for x in [r_pref.status_code, r_webhooks.status_code, r_profile.status_code])
results["PreferencesAndSettings"] = {
    "preferences_status": r_pref.status_code,
    "webhooks_status": r_webhooks.status_code,
    "profile_status": r_profile.status_code,
    "all_ok": v8_ok
}

all_views_passed = all(v["all_ok"] for v in results.values())
print("\n" + "="*50)
print(f"ALL 8 WORKSPACE VIEWS VERIFIED: {all_views_passed}")
print("="*50)

with open(os.path.join(REPO_DIR, "workspace_verification_results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

if not all_views_passed:
    sys.exit(1)
print("\n[SUCCESS] All 8 workspace views verified via real Next.js BFF!")
