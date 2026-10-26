"""
Minimal backend for the AI-CRM prototype.


Cfare ben:
1. Tregon fundin e nje /chat dhe e con biseden te Claude duke perdorur nje prompt sistemi + save_lead
2. Suporton gjuhen e zgjedhur nga user dhe prompti i sistemit e lock Claude ne ate gjuhe.
3. Numeron se sa here klienti ka refuzuar kerkesen per kontakt me ane te nje pjese kodi ne vend qe te besoj Claude pasi testi
   tregoi qe LLM nuk jane shume te besueshme ne marjen e vendimeve.
4. Nese Claude vendos qe informacioni mjafton, therret save_lead dhe e fut lead ne nje SQLite database dhe perfundon.
5. Ne te kundert Claude i kthehet pyetjeve qe chati te vazhdoje.
6/ /leads lejon dashboardin te tregoje cfare leadsash jane kapur deri tani.
7. /leads/stats i kthen dashboardit numra te perbledhur (total, sipas statusit, gjuhes, dhe 7 diteve te fundit).
8. Nese SMTP eshte konfiguruar ne .env, dergon nje email njoftimi cdo here qe nje lead ruhet - nese dergimi deshton, gabimi kapet dhe /chat vazhdon normalisht.
9. /leads/{id}/assign lejon dashboardin t'i caktoje nje lead nje agjenti shitjesh.
10. POST /leads lejon nje administrator te shtoje manualisht nje lead te ri nga dashboardi.
11. /leads/{id}/edit lejon nje administrator te korrigjoje detajet e nje lead ekzistues (emer, kontakt, nevoje, afat).

"""

import os
import re
import smtplib
import sqlite3
from contextlib import contextmanager
from email.message import EmailMessage

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic

load_dotenv()

API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-haiku-4-5-20251001"
DB_PATH = os.getenv("DB_PATH", "leads.db")

# Email notification settings (optional) - if any of these are missing, lead
# notifications are silently skipped rather than breaking /chat. Set these in
# your .env file to enable them:
#   SMTP_HOST=smtp.gmail.com
#   SMTP_PORT=587
#   SMTP_USER=youraddress@gmail.com
#   SMTP_PASSWORD=your-app-specific-password
#   NOTIFY_EMAIL_TO=where-to-send-notifications@example.com
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
NOTIFY_EMAIL_TO = os.getenv("NOTIFY_EMAIL_TO")


# Gjuhet e lejuara nga chatboti.
SUPPORTED_LANGUAGES = {"English", "Italian"}
DEFAULT_LANGUAGE = "English"

# Statuset e pipelineve qe dashboardi lejon.
ALLOWED_STATUSES = {"new", "contacted", "qualified", "not interested"}

app = FastAPI(title="AI-CRM Lead Capture Prototype")

# Lejon chat widget ose dashboard te therrase kete API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=API_KEY) if API_KEY else None

# Prompti
SYSTEM_PROMPT_TEMPLATE = """You are a friendly sales assistant collecting a lead's name, contact info, need, and timeline through natural conversation.

You can only talk about topics related to dental care and cosmetic surgery procedures. If the client tries to talk about things unrelated to dental care or cosmetic surgery procedures politely refuse to talk about things unrelated to them.

Ask exactly one question at a time, in this order: first ask what brings them in / what they need, then their name, then their contact information (phone or email), then their preferred timeline. Do not skip ahead or ask multiple questions at once.

If the lead is hesitant to share contact information, don't give up immediately - ask up to two times total, rephrasing each time and briefly explaining why it's needed. Count only the user's refusals, not how many different contact methods you've suggested. If the client has refused 2 total times suggest them to contact the clinic at +355 67 608 4446.

Once you have all four fields (or contact was explicitly declined), call the save_lead tool.

If the client asks about prices explain to them that the pricing may differ and for that it is better to be contacted from someone from Azalea's team.

Keep responses professional and don't use emojis.

Respond only in {language}. Do not switch to another language even if the user writes in a different one."""

SAVE_LEAD_TOOL = {
    "name": "save_lead",
    "description": "Save a qualified lead once all required fields are collected.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "contact": {"type": "string"},
            "need": {"type": "string"},
            "timeline": {"type": "string"},
        },
        "required": ["name", "contact", "need", "timeline"],
    },
}


# Numerimi i refuzimeve (ne kod, nuk i eshte lene modelit per te numeruar)
# Gjate testimeve u zbulua se LLM nuk jane te dobishme ne numerimin preciz te
# refuzimeve nga klienti dhe eshte me e lehte ti detektojme refuzimet me ane te
# kodit se sa te forcojme sjelljen me ane te instruksioneve.

EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE_RE = re.compile(r"\+?\d[\d\-\s()]{6,}\d")
CONTACT_ASK_KEYWORDS = ("phone", "email", "e-mail", "contact", "reach you", "website", "number")


def count_contact_refusals(messages: list[dict]) -> int:
    # Numeron sa here chatboti pyeti per kontakt dhe kontrollon mesazhin pasardhes
    # te klientin nese permban ndonje gje qe duket si email apo nr telefoni
    refusals = 0
    for i in range(len(messages) - 1):
        m = messages[i]
        nxt = messages[i + 1]
        if m["role"] == "assistant" and nxt["role"] == "user":
            asked_for_contact = any(k in m["content"].lower() for k in CONTACT_ASK_KEYWORDS)
            gave_contact = bool(EMAIL_RE.search(nxt["content"]) or PHONE_RE.search(nxt["content"]))
            if asked_for_contact and not gave_contact:
                refusals += 1
    return refusals


FORCE_DECLINE_INSTRUCTION = (
    "\n\nThe user has now been asked for contact information at least twice without "
    "providing anything that looks like an email or phone number. Do not ask again "
    "under any circumstances, and do not offer another alternative contact method. "
    "Call save_lead immediately, using whatever other fields have been gathered so "
    "far and setting contact to 'declined'."
)



# Database

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                contact TEXT,
                need TEXT,
                timeline TEXT,
                language TEXT DEFAULT 'English',
                transcript TEXT,
                status TEXT DEFAULT 'new',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Lightweight migration: databases created before the agent-assignment
        # feature was added won't have this column yet. ALTER TABLE ... ADD
        # COLUMN is safe to run once; we check first so re-running init_db()
        # (e.g. on every server restart) doesn't error on the second run.
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(leads)").fetchall()}
        if "assigned_to" not in existing_cols:
            conn.execute("ALTER TABLE leads ADD COLUMN assigned_to TEXT")


init_db()


def save_lead_to_db(lead: dict, transcript: str, language: str) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO leads (name, contact, need, timeline, language, transcript) VALUES (?, ?, ?, ?, ?, ?)",
            (lead.get("name"), lead.get("contact"), lead.get("need"), lead.get("timeline"), language, transcript),
        )
        return cur.lastrowid


def send_lead_notification_email(lead: dict, language: str) -> None:
    """Best-effort email notification when a new lead is saved. Any failure
    here is logged and swallowed rather than raised, so a misconfigured or
    unreachable mail server never breaks the /chat endpoint for the visitor."""
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD and NOTIFY_EMAIL_TO):
        print("[email] Notification skipped - SMTP settings not fully configured in .env")
        return

    msg = EmailMessage()
    msg["Subject"] = f"New lead captured: {lead.get('name', 'Unknown')}"
    msg["From"] = SMTP_USER
    msg["To"] = NOTIFY_EMAIL_TO
    msg.set_content(
        "A new lead was captured by the chatbot.\n\n"
        f"Name: {lead.get('name', '-')}\n"
        f"Contact: {lead.get('contact', '-')}\n"
        f"Need: {lead.get('need', '-')}\n"
        f"Timeline: {lead.get('timeline', '-')}\n"
        f"Language: {language}\n"
    )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"[email] Notification sent for lead: {lead.get('name', 'Unknown')}")
    except Exception as e:
        # Never let a mail failure break the chat flow for the visitor.
        print(f"[email] Failed to send lead notification: {e}")


# API models

class Message(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    language: str = DEFAULT_LANGUAGE


class UpdateStatusRequest(BaseModel):
    status: str


class AssignLeadRequest(BaseModel):
    assigned_to: str


class CreateLeadRequest(BaseModel):
    name: str
    contact: str
    need: str
    timeline: str
    language: str = DEFAULT_LANGUAGE
    status: str = "new"


class EditLeadRequest(BaseModel):
    name: str | None = None
    contact: str | None = None
    need: str | None = None
    timeline: str | None = None


# Routes

@app.get("/")
def health():
    return {"status": "ok", "api_key_configured": bool(API_KEY)}


@app.post("/chat")
def chat(req: ChatRequest):
    if not client:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY is not set. Create a .env file (see .env.example).",
        )

    language = req.language if req.language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    claude_messages = [{"role": m.role, "content": m.content} for m in req.messages]

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(language=language)
    if count_contact_refusals(claude_messages) >= 2:
        system_prompt += FORCE_DECLINE_INSTRUCTION

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=system_prompt,
            messages=claude_messages,
            tools=[SAVE_LEAD_TOOL],
        )
    except anthropic.APIError as e:
        # Bubble up a clean error instead of a stack trace - e.g. bad API key,
        # rate limit, insufficient credit, or a network problem reaching Anthropic.
        status = getattr(e, "status_code", 502)
        raise HTTPException(status_code=status, detail=str(e))

    if response.stop_reason == "tool_use":
        tool_block = next(b for b in response.content if b.type == "tool_use")
        lead_data = tool_block.input
        transcript = "\n".join(f"{m.role}: {m.content}" for m in req.messages)
        lead_id = save_lead_to_db(lead_data, transcript, language)
        send_lead_notification_email(lead_data, language)
        return {"status": "lead_saved", "lead_id": lead_id, "lead": lead_data}

    # Otherwise, Claude just wants to keep the conversation going.
    text_block = next((b for b in response.content if b.type == "text"), None)
    reply = text_block.text if text_block else ""
    return {"status": "continue", "reply": reply}


@app.get("/leads")
def list_leads():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


@app.get("/leads/stats")
def lead_stats():
    """Simple aggregate counts for the dashboard's analytics section."""
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM leads").fetchone()["c"]
        by_status_rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM leads GROUP BY status"
        ).fetchall()
        by_language_rows = conn.execute(
            "SELECT language, COUNT(*) AS c FROM leads GROUP BY language"
        ).fetchall()
        by_day_rows = conn.execute(
            """
            SELECT date(created_at) AS day, COUNT(*) AS c
            FROM leads
            WHERE date(created_at) >= date('now', '-6 days')
            GROUP BY day
            ORDER BY day
            """
        ).fetchall()

    return {
        "total": total,
        "by_status": {row["status"] or "new": row["c"] for row in by_status_rows},
        "by_language": {row["language"] or "English": row["c"] for row in by_language_rows},
        "by_day": {row["day"]: row["c"] for row in by_day_rows},
    }


@app.patch("/leads/{lead_id}")
def update_lead_status(lead_id: int, req: UpdateStatusRequest):
    if req.status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(ALLOWED_STATUSES)}",
        )
    with get_db() as conn:
        cur = conn.execute("UPDATE leads SET status = ? WHERE id = ?", (req.status, lead_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return dict(row)


@app.patch("/leads/{lead_id}/assign")
def assign_lead(lead_id: int, req: AssignLeadRequest):
    """Assigns (or unassigns) a lead to a sales agent. Any non-empty string is
    accepted here rather than validating against a fixed server-side list, so
    the dashboard's agent list (currently a small hardcoded array in
    dashboard.html) can be edited freely without needing a backend change."""
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE leads SET assigned_to = ? WHERE id = ?", (req.assigned_to, lead_id)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return dict(row)


@app.post("/leads")
def create_lead(req: CreateLeadRequest):
    """Lets an administrator add a lead manually from the dashboard - for
    example, a phone or walk-in enquiry that never went through the chatbot.
    The transcript field is set to a fixed note rather than left blank, so
    it's clear in the dashboard that this record didn't originate from a
    chatbot conversation."""
    language = req.language if req.language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    status = req.status if req.status in ALLOWED_STATUSES else "new"
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO leads (name, contact, need, timeline, language, transcript, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (req.name, req.contact, req.need, req.timeline, language,
             "(added manually by an administrator - no chatbot transcript)", status),
        )
        lead_id = cur.lastrowid
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return dict(row)


@app.patch("/leads/{lead_id}/edit")
def edit_lead(lead_id: int, req: EditLeadRequest):
    """Lets an administrator correct a lead's captured details (for example,
    a mistyped email) directly from the dashboard. Only the fields actually
    provided in the request body are updated; omitted fields are left as-is."""
    fields = {}
    if req.name is not None:
        fields["name"] = req.name
    if req.contact is not None:
        fields["contact"] = req.contact
    if req.need is not None:
        fields["need"] = req.need
    if req.timeline is not None:
        fields["timeline"] = req.timeline

    if not fields:
        raise HTTPException(status_code=400, detail="no fields provided to update")

    set_clause = ", ".join(f"{col} = ?" for col in fields)
    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE leads SET {set_clause} WHERE id = ?",
            (*fields.values(), lead_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="lead not found")
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return dict(row)
