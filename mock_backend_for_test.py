"""
Throwaway mock backend used ONLY to test run_eval.py's harness logic
(HTTP loop, scoring, report writing) without needing a real Anthropic API key.
Mimics the shape of /chat responses with simple regex-based "extraction" -
not meant to resemble real chatbot quality, just the response contract.
Deliberately makes one scenario (S3) never complete, to verify the harness
handles a max-turns-reached case without crashing.
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

    # Deliberately never finish this one, to test max-turns handling in the harness.
    if "not really sure when" in all_text:
        return jsonify({"status": "continue", "reply": "Could you give me any timeframe at all?"})

    email_match = EMAIL_RE.search(all_text)
    name_match = NAME_RE.search(all_text)

    refusal_count = all_text.lower().count("rather not share") + all_text.lower().count("still don't want")

    if refusal_count >= 2:
        return jsonify({
            "status": "lead_saved",
            "lead_id": 1,
            "lead": {
                "name": name_match.group(1) if name_match else "Unknown",
                "contact": "declined",
                "need": "unspecified",
                "timeline": "unspecified",
            },
        })

    if email_match and name_match:
        return jsonify({
            "status": "lead_saved",
            "lead_id": 1,
            "lead": {
                "name": name_match.group(1),
                "contact": email_match.group(0),
                "need": "cleaning",
                "timeline": "soon",
            },
        })

    return jsonify({"status": "continue", "reply": "Could you tell me more, and share your name and email?"})


if __name__ == "__main__":
    app.run(port=8123)
