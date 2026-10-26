"""
Verifies PATCH /leads/{id} without touching the Anthropic API at all,
since this endpoint doesn't call Claude.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ["ANTHROPIC_API_KEY"] = "sk-test-fake-key"
os.environ["DB_PATH"] = os.path.join(os.path.dirname(__file__), "_test_leads3.db")
if os.path.exists(os.environ["DB_PATH"]):
    os.remove(os.environ["DB_PATH"])

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app)


def assert_(cond, msg):
    if not cond:
        print("FAILED:", msg)
        sys.exit(1)


# Seed a lead directly via the DB helper (bypassing /chat since it needs Claude).
lead_id = main.save_lead_to_db(
    {"name": "Marco", "contact": "marco@example.it", "need": "CRM", "timeline": "1 month"},
    transcript="user: hi\nassistant: hello",
    language="English",
)

# 1. Default status should be 'new'
resp = client.get("/leads")
leads = resp.json()
assert_(len(leads) == 1, f"expected 1 lead, got {len(leads)}")
assert_(leads[0]["status"] == "new", f"expected default status 'new', got {leads[0]['status']}")
print("Test 1 passed: new lead defaults to status 'new'")

# 2. Valid status update
resp = client.patch(f"/leads/{lead_id}", json={"status": "contacted"})
assert_(resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}")
assert_(resp.json()["status"] == "contacted", "status should be updated to 'contacted'")
print("Test 2 passed: valid status update works")

# 3. Invalid status should be rejected with 400, not silently accepted
resp = client.patch(f"/leads/{lead_id}", json={"status": "banana"})
assert_(resp.status_code == 400, f"expected 400 for invalid status, got {resp.status_code}")
print("Test 3 passed: invalid status rejected with 400")

# 4. Updating a nonexistent lead should 404
resp = client.patch("/leads/99999", json={"status": "qualified"})
assert_(resp.status_code == 404, f"expected 404 for nonexistent lead, got {resp.status_code}")
print("Test 4 passed: nonexistent lead returns 404")

# 5. Confirm the update persisted (not just returned in the response)
resp = client.get("/leads")
leads = resp.json()
assert_(leads[0]["status"] == "contacted", "status change should persist across requests")
print("Test 5 passed: status change persists in the database")

print("\nALL STATUS ENDPOINT TESTS PASSED")
