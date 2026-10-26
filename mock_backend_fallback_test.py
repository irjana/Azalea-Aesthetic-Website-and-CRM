"""
Throwaway mock used only to test run_eval.py's NEW catch-all fallback logic.
Deliberately withholds lead_saved until it sees a message containing the
word "make sure" (which is exactly the phrasing build_fallback_message()
uses), to prove the fallback path actually gets exercised and works - and
for one specific case, never saves at all, to confirm the harness handles
that gracefully (no crash, no infinite loop, correctly reported as failed).
"""
import re
from flask import Flask, request, jsonify

app = Flask(__name__)

EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
NAME_RE = re.compile(r"(?:I'?m|I am|name is|call me)\s+([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)")


@app.route("/chat", methods=["POST"])
def chat():
    body = request.get_json()
    messages = body["messages"]
    all_text = " ".join(m["content"] for m in messages if m["role"] == "user")

    # S5-style: never save, to confirm the harness doesn't crash or hang,
    # and confirm NO fallback message gets sent (contact is expected 'declined').
    if "braces" in all_text.lower():
        return jsonify({"status": "continue", "reply": "Could you tell me your timeline?"})

    # Deliberately withhold saving until the consolidated fallback message
    # arrives, to prove the fallback path is what completes the scenario.
    if "make sure everything is clear" in all_text.lower():
        email_match = EMAIL_RE.search(all_text)
        name_match = NAME_RE.search(all_text)
        return jsonify({
            "status": "lead_saved",
            "lead_id": 1,
            "lead": {
                "name": name_match.group(1) if name_match else "Unknown",
                "contact": email_match.group(0) if email_match else "unknown",
                "need": "cleaning",
                "timeline": "soon",
            },
        })

    return jsonify({"status": "continue", "reply": "Could you also give me one more detail?"})


if __name__ == "__main__":
    app.run(port=8124)
