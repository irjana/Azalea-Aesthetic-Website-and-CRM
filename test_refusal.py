"""
Verifies count_contact_refusals() and the forced-decline instruction wiring,
using the exact conversation shape reported as failing, without hitting the
real Anthropic API.
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(__file__))
os.environ["ANTHROPIC_API_KEY"] = "sk-test-fake-key"
os.environ["DB_PATH"] = os.path.join(os.path.dirname(__file__), "_test_leads2.db")
if os.path.exists(os.environ["DB_PATH"]):
    os.remove(os.environ["DB_PATH"])

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app)


def assert_(cond, msg):
    if not cond:
        print("FAILED:", msg)
        sys.exit(1)


# --- Unit test the counter directly against the exact reported conversation ---
conversation = [
    {"role": "user", "content": "I'm looking for information about a treatment."},
    {"role": "assistant", "content": "Of course. Could I get your name?"},
    {"role": "user", "content": "It's Elira."},
    {"role": "assistant", "content": "Thanks Elira. Could I get a phone number or email to follow up?"},
    {"role": "user", "content": "I'd rather not share that."},
    {"role": "assistant", "content": "No problem, even a general way to reach you would help."},
    {"role": "user", "content": "I still don't want to share it."},
]
count = main.count_contact_refusals(conversation)
assert_(count == 2, f"expected 2 refusals detected, got {count}")
print("Test 1 passed: counter detects exactly 2 refusals in the reported conversation")

# --- One refusal only -> should NOT force decline yet ---
one_refusal = conversation[:5]  # up through the first refusal only
count1 = main.count_contact_refusals(one_refusal)
assert_(count1 == 1, f"expected 1 refusal, got {count1}")
print("Test 2 passed: only 1 refusal counted before the second decline")

# --- Providing an email should NOT count as a refusal ---
gave_email = [
    {"role": "assistant", "content": "Could I get an email or phone number?"},
    {"role": "user", "content": "Sure, it's elira@example.com"},
]
count2 = main.count_contact_refusals(gave_email)
assert_(count2 == 0, f"expected 0 refusals when an email is actually given, got {count2}")
print("Test 3 passed: giving a real email is not counted as a refusal")


# --- Full /chat integration: 2 refusals should force tool_use with contact='declined' ---
captured = []


def fake_create(**kwargs):
    captured.append(kwargs)
    # Simulate what SHOULD happen once the forced instruction is present:
    # the model complies and calls save_lead with contact declined.
    if "FORCE_DECLINE" in kwargs["system"] or "at least twice" in kwargs["system"]:
        tool_block = types.SimpleNamespace(
            type="tool_use",
            name="save_lead",
            input={"name": "Elira", "contact": "declined", "need": "treatment info", "timeline": "unspecified"},
        )
        return types.SimpleNamespace(stop_reason="tool_use", content=[tool_block])
    text_block = types.SimpleNamespace(type="text", text="(would ask again)")
    return types.SimpleNamespace(stop_reason="end_turn", content=[text_block])


main.client.messages.create = fake_create

resp = client.post("/chat", json={"messages": conversation, "language": "English"})
assert_(resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}")
sent_system = captured[-1]["system"]
assert_("at least twice" in sent_system, "system prompt should include the forced-decline instruction after 2 refusals")
body = resp.json()
assert_(body["status"] == "lead_saved", f"expected lead_saved, got {body}")
assert_(body["lead"]["contact"] == "declined", "lead contact should be 'declined'")
print("Test 4 passed: after 2 refusals, forced instruction is injected and lead is saved with contact='declined'")

# --- Sanity: with only 1 refusal, the forced instruction should NOT be injected ---
resp2 = client.post("/chat", json={"messages": one_refusal, "language": "English"})
sent_system2 = captured[-1]["system"]
assert_("at least twice" not in sent_system2, "forced instruction should NOT appear after only 1 refusal")
print("Test 5 passed: forced instruction absent after only 1 refusal")

print("\nALL REFUSAL-COUNTING TESTS PASSED")
