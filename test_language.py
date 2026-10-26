"""
Verifies the language-selection wiring in main.py without hitting the real
Anthropic API (mocks client.messages.create). Run from the same folder as main.py.
"""
import types
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

os.environ["ANTHROPIC_API_KEY"] = "sk-test-fake-key"
os.environ["DB_PATH"] = os.path.join(os.path.dirname(__file__), "_test_leads.db")
if os.path.exists(os.environ["DB_PATH"]):
    os.remove(os.environ["DB_PATH"])

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app)

captured_calls = []


def fake_create(**kwargs):
    captured_calls.append(kwargs)
    # Mimic a plain "continue" style response (a text block, no tool use).
    text_block = types.SimpleNamespace(type="text", text="(mock reply)")
    return types.SimpleNamespace(stop_reason="end_turn", content=[text_block])


main.client.messages.create = fake_create

def assert_(cond, msg):
    if not cond:
        print("FAILED:", msg)
        sys.exit(1)

# --- Test 1: default language (no "language" field sent) should be English ---
resp = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
assert_(resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}")
sent_system = captured_calls[-1]["system"]
assert_("Respond only in English" in sent_system, "default language should default to English in the system prompt")
print("Test 1 passed: default language -> English")

# --- Test 2: explicit Italian ---
resp = client.post("/chat", json={"messages": [{"role": "user", "content": "ciao"}], "language": "Italian"})
assert_(resp.status_code == 200, f"expected 200, got {resp.status_code}")
sent_system = captured_calls[-1]["system"]
assert_("Respond only in Italian" in sent_system, "should instruct the model to respond in Italian")
print("Test 2 passed: language=Italian -> system prompt says Italian")

# --- Test 3: unsupported language falls back to English instead of injecting garbage ---
resp = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}], "language": "Klingon"})
assert_(resp.status_code == 200, f"expected 200, got {resp.status_code}")
sent_system = captured_calls[-1]["system"]
assert_("Respond only in English" in sent_system, "unsupported language should fall back to English")
assert_("Klingon" not in sent_system, "unsupported language string should not leak into the system prompt")
print("Test 3 passed: unsupported language -> falls back to English safely")

# --- Test 4: tool_use path still works and now stores language on the lead ---
def fake_create_tool_use(**kwargs):
    captured_calls.append(kwargs)
    tool_block = types.SimpleNamespace(
        type="tool_use",
        name="save_lead",
        input={"name": "Marco", "contact": "marco@example.it", "need": "CRM", "timeline": "1 mese"},
    )
    return types.SimpleNamespace(stop_reason="tool_use", content=[tool_block])

main.client.messages.create = fake_create_tool_use

resp = client.post("/chat", json={
    "messages": [{"role": "user", "content": "Sono Marco, marco@example.it, mi serve un CRM, entro un mese"}],
    "language": "Italian",
})
assert_(resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}")
body = resp.json()
assert_(body["status"] == "lead_saved", "expected lead_saved status")
assert_(body["lead"]["name"] == "Marco", "expected extracted name to round-trip")
print("Test 4 passed: tool_use path saves lead correctly with language field")

leads_resp = client.get("/leads")
assert_(leads_resp.status_code == 200, "GET /leads should return 200")
leads = leads_resp.json()
assert_(len(leads) == 1, f"expected 1 saved lead, got {len(leads)}")
assert_(leads[0]["language"] == "Italian", "saved lead should record language=Italian")
print("Test 5 passed: /leads shows the saved lead with language recorded")

print("\nALL TESTS PASSED")
