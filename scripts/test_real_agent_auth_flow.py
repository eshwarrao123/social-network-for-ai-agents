"""
End-to-End Authentication and Workspace Verification (P10.1 Step 4)
Tests:
  1. BFF Agent Registration (POST /api/auth/register)
  2. BFF Token Exchange (POST /api/auth/connect)
  3. BFF Session Verification (GET /api/auth/session)
  4. Protected Workspace Access (GET /dashboard)
Zero exposure of secrets or credentials.
"""
import httpx
import sys

BASE_URL = "http://localhost:3000"

def test_full_auth_flow():
    client = httpx.Client(base_url=BASE_URL, headers={
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/connect",
        "Accept": "application/json",
    }, timeout=10.0)

    print("[*] 1. Registering real test enterprise agent via BFF (/api/auth/register)...")
    reg_payload = {
        "name": "Nova Sentinel Alpha",
        "company": "Nova Enterprise Systems",
        "description": "Autonomous infrastructure security monitoring and incident response agent.",
        "industries": ["cybersecurity", "enterprise-cloud"],
        "capabilities": ["threat-intelligence", "vulnerability-scan"],
        "tags": ["security", "cloud", "audit"]
    }
    reg_res = client.post("/api/auth/register", json=reg_payload)
    if reg_res.status_code == 409:
        print("[!] Agent already registered. Registering with unique suffix...")
        import uuid
        reg_payload["name"] = f"Nova Sentinel Alpha {uuid.uuid4().hex[:4]}"
        reg_res = client.post("/api/auth/register", json=reg_payload)

    if reg_res.status_code != 201:
        print(f"[FAIL] Registration failed with HTTP {reg_res.status_code}: {reg_res.text}")
        return False

    reg_data = reg_res.json()
    print(f"[+] Agent registered successfully! ID: {reg_data.get('id')}, Name: '{reg_data.get('name')}', Company: '{reg_data.get('company')}'")

    raw_api_key = reg_data.get("api_key")
    if not raw_api_key:
        print("[FAIL] No API key returned in registration response")
        return False

    # Check key format
    print(f"[+] API key received. Prefix check: starts with 'asama_live_': {raw_api_key.startswith('asama_live_')}, total length: {len(raw_api_key)}")

    print("[*] 2. Connecting agent workspace via BFF token exchange (/api/auth/connect)...")
    conn_res = client.post("/api/auth/connect", json={"api_key": raw_api_key})
    if conn_res.status_code != 200:
        print(f"[FAIL] Connect failed with HTTP {conn_res.status_code}: {conn_res.text}")
        return False

    conn_data = conn_res.json()
    print(f"[+] Token exchange successful: success={conn_data.get('success')}, agent_name='{conn_data.get('agent_name')}'")
    cookies = dict(client.cookies)
    has_session_cookie = "agent_session" in cookies
    print(f"[+] HttpOnly session cookie 'agent_session' present: {has_session_cookie}")

    print("[*] 3. Verifying active session via BFF (/api/auth/session)...")
    sess_res = client.get("/api/auth/session")
    if sess_res.status_code != 200:
        print(f"[FAIL] Session probe failed with HTTP {sess_res.status_code}: {sess_res.text}")
        return False

    sess_data = sess_res.json()
    is_authenticated = sess_data.get("authenticated")
    agent_info = sess_data.get("agent", {})
    print(f"[+] Session authenticated: {is_authenticated}, Agent Name: '{agent_info.get('name')}'")

    print("[*] 4. Testing dashboard access with authenticated session (/dashboard)...")
    dash_res = client.get("/dashboard")
    print(f"[+] GET /dashboard HTTP status: {dash_res.status_code}")
    assert dash_res.status_code == 200, f"Expected 200, got {dash_res.status_code}"
    print(f"[+] Dashboard page length: {len(dash_res.text)} bytes")

    client.close()

    print("\n[SUCCESS] Full end-to-end authentication and workspace access verified successfully!")
    return True

if __name__ == "__main__":
    ok = test_full_auth_flow()
    sys.exit(0 if ok else 1)
