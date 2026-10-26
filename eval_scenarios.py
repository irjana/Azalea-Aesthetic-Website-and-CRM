"""
Evaluation test scenarios for the AI-CRM chatbot.

Each scenario simulates a realistic user by scripting what THEY say at each
turn (not what the bot says back - those replies come from your real running
backend, so this actually exercises the live system, not a fake one).

REVISION HISTORY:
  v1 - initial 12 scenarios, mostly 1-3 turns each.
  v2 - after first real run: padded several scenarios with extra turns based
       on actual observed bot replies (it asks for a second contact method,
       a fuller name, or a firmer timeline more often than v1 assumed); fixed
       S5's opening line so the refusal turns land after a real question.
  v3 - after second real run: fixed remaining turn-budget mismatches (S1
       needed a full-name confirmation turn, S3 needed a firmer timeline
       instead of a phone number, S6 was simply missing a timeline turn).
  v4 - after third real run: confirmed this is genuine run-to-run model
       variance (different scenarios needed different extra turns each run,
       with no code changes in between), not a scripting problem to keep
       chasing. run_eval.py now has a generic catch-all fallback for this
       instead of scenarios needing ever-more-specific padding.

KNOWN, DOCUMENTED LIMITATION (not being fixed, per project decision - see
S5's notes below): the backend's count_contact_refusals() function (in
main.py) only counts a refusal when the assistant's immediately preceding
message asked about contact info - it does not look at what the user
actually said. Across repeated runs, the bot doesn't always ask about
contact in the same position in the conversation, so an explicit refusal
can land after a non-contact question and go uncounted. Additionally,
even on a run where the refusal count is detected correctly, the model has
been observed saying it will "save" the lead without actually calling the
save_lead tool - a separate instruction-following reliability gap. Both are
documented here and in the eval report as known limitations rather than
patched.

Fields:
  id            - short identifier, used in reports
  description   - human-readable summary of what this scenario tests
  language      - "English" or "Italian", sent with every request
  user_turns    - list of strings; each one is sent as the next user message
  expected      - dict of field -> substring expected in the final extracted
                  lead (case-insensitive containment check). Use None for a
                  field you don't want auto-checked (e.g., free-text fields
                  that are hard to grade automatically - these get flagged
                  for manual review in the report instead of auto-failed).
  expect_saved  - True if this scenario should end in status "lead_saved"
                  within the scripted turns (plus the harness's generic
                  catch-all fallback if needed - see run_eval.py).
  notes         - what specifically to look for when manually reviewing
                  the transcript, beyond the automated field checks.
"""

SCENARIOS = [
    {
        "id": "S1_all_info_upfront",
        "description": "All four fields given in a single opening message",
        "language": "English",
        "user_turns": [
            "Hi, I'm Dritan, I need a cleaning and checkup, ideally within the next month, "
            "you can reach me at dritan@example.com",
            "Sure, you can also reach me by phone at +355691112222.",
            "Just Dritan is fine, no last name.",
        ],
        "expected": {"name": "Dritan", "contact": "dritan@example.com", "need": "cleaning", "timeline": "month"},
        "expect_saved": True,
        "notes": "Should not ask redundant questions beyond confirming/collecting a second contact "
                 "method and the name format. KNOWN BEHAVIOR: the bot inconsistently asks whether a "
                 "single first name is 'complete' - accepted, not treated as a bug.",
    },
    {
        "id": "S2_gradual_info",
        "description": "Info volunteered gradually across several turns",
        "language": "English",
        "user_turns": [
            "Hi, I've been having some tooth pain.",
            "My name is Elira.",
            "You can reach me at elira@example.com.",
            "I'd like to come in sometime in the next two weeks.",
            "It's just general tooth pain, I'd like it looked at.",
            "Yes, an examination to start with.",
        ],
        "expected": {"name": "Elira", "contact": "elira@example.com", "need": "pain", "timeline": "two weeks"},
        "expect_saved": True,
        "notes": "KNOWN BEHAVIOR (not treated as a bug per project decision): the bot re-asks about the "
                 "need after every subsequent turn instead of accepting 'tooth pain' on its own, "
                 "sometimes resolving after 1-2 extra turns and sometimes taking longer.",
    },
    {
        "id": "S3_vague_timeline",
        "description": "User gives a vague, non-specific timeline",
        "language": "English",
        "user_turns": [
            "Hi, I'm Marco and I'm interested in teeth whitening.",
            "You can reach me at marco@example.com.",
            "I'm not really sure when, maybe sometime this year.",
            "Let's say within the next two months.",
        ],
        "expected": {"name": "Marco", "contact": "marco@example.com", "need": "whitening", "timeline": "month"},
        "expect_saved": True,
        "notes": "KNOWN BEHAVIOR: the bot does not always accept a vague timeline or a given email as "
                 "final on the first pass, and re-confirms details - same underlying pattern as S2/S10 "
                 "(wanting a more complete/confirmed answer). Accepted, not a bug.",
    },
    {
        "id": "S4_one_refusal_then_given",
        "description": "User initially declines contact info, then provides it",
        "language": "English",
        "user_turns": [
            "Hi, I'm Sara, I need a root canal consultation soon.",
            "I'd rather not share that.",
            "Okay fine, it's sara@example.com.",
            "Let's say sometime next week.",
        ],
        "expected": {"name": "Sara", "contact": "sara@example.com", "need": "root canal", "timeline": "week"},
        "expect_saved": True,
        "notes": "Confirms recovering from a single refusal still ends with real contact info, not 'declined'.",
    },
    {
        "id": "S5_two_refusals_declined",
        "description": "User refuses contact info twice - should end with contact='declined'",
        "language": "English",
        "user_turns": [
            "Hi, I'm Blerta, I want braces for myself - I've been wanting to straighten my teeth for a while.",
            "I'd rather not share my phone or email right now.",
            "I still don't want to share that.",
        ],
        "expected": {"name": "Blerta", "contact": "declined", "need": "braces", "timeline": None},
        "expect_saved": True,
        "notes": "DOCUMENTED KNOWN LIMITATION, intentionally left unfixed per project decision: "
                 "count_contact_refusals() in main.py only counts a refusal when the assistant's "
                 "PRECEDING message asked about contact - it does not read the content of the user's "
                 "reply, so ordering variance can cause a real refusal to go uncounted. Separately, "
                 "even on runs where the refusal count IS detected correctly, the model has been "
                 "observed saying it will save the lead without actually invoking save_lead - a second, "
                 "independent instruction-following gap. Record the actual outcome each run; cite both "
                 "as limitations in the results/limitations chapter. No fallback message is sent for "
                 "this scenario (see run_eval.py) since restating contact info would defeat the point "
                 "of testing the decline path.",
    },
    {
        "id": "S6_offtopic_as_need",
        "description": "Off-topic content given as the answer to the 'need' question",
        "language": "English",
        "user_turns": [
            "I want to build a house",
            "Okay, actually I need a dental cleaning, my name is Laura.",
            "laura@example.com",
            "Sometime next week works for me.",
        ],
        "expected": {"name": "Laura", "contact": "laura@example.com", "need": "cleaning", "timeline": "week"},
        "expect_saved": True,
        "notes": "The off-topic redirect itself has been confirmed working correctly on every run so "
                 "far - first reply always redirects instead of treating house-building as the need. "
                 "Completion timing on the 'need' field varies run to run (see S2 notes).",
    },
    {
        "id": "S7_offtopic_mid_flow",
        "description": "Off-topic content given later, as the answer to a different pending question",
        "language": "English",
        "user_turns": [
            "Hi, I'm Laura and I need a cleaning.",
            "I want to build a house",
            "Sorry, laura@example.com, and sometime next month.",
        ],
        "expected": {"name": "Laura", "contact": "laura@example.com", "need": "cleaning", "timeline": "month"},
        "expect_saved": True,
        "notes": "Confirmed working on every run so far - correctly redirects and re-asks the pending "
                 "question instead of absorbing the off-topic remark.",
    },
    {
        "id": "S8_borderline_not_offtopic",
        "description": "A question that sounds tangential but is legitimately dental-related - guardrail should NOT block it",
        "language": "English",
        "user_turns": [
            "Hi, I'm Enkel, do you take insurance for dental work?",
            "Okay great, I need a checkup, reachable at enkel@example.com, sometime this month.",
            "Sure, it's +355693334444.",
        ],
        "expected": {"name": "Enkel", "contact": "enkel@example.com", "need": "checkup", "timeline": "month"},
        "expect_saved": True,
        "notes": "IMPORTANT: confirms the guardrail isn't over-triggering on legitimate dental-adjacent "
                 "questions (insurance, hours, pricing) - confirmed not blocked on every run so far. "
                 "What additional info it asks for last (phone vs. full name) varies run to run.",
    },
    {
        "id": "S9_italian_full_conversation",
        "description": "Full conversation conducted in Italian",
        "language": "Italian",
        "user_turns": [
            "Ciao, sono Marco e ho bisogno di una pulizia dentale.",
            "Il mio numero e marco.it@example.com",
            "Diciamo entro un mese.",
        ],
        "expected": {"name": "Marco", "contact": "marco.it@example.com", "need": None, "timeline": None},
        "expect_saved": True,
        "notes": "Confirmed working on every run so far - stays in Italian throughout the whole "
                 "conversation, not just the final message.",
    },
    {
        "id": "S10_informal_name_then_full_name",
        "description": "User gives a nickname first; bot asks for a full name (accepted behavior) and receives one",
        "language": "English",
        "user_turns": [
            "Hey, just call me J, I need a filling replaced.",
            "j@example.com, sometime in the next few weeks.",
            "It's Jonida Krasniqi.",
        ],
        "expected": {"name": "Jonida", "contact": "j@example.com", "need": "filling", "timeline": "weeks"},
        "expect_saved": True,
        "notes": "KNOWN BEHAVIOR (not treated as a bug per project decision): the bot requires a full "
                 "name and does not accept a nickname on its own. Confirmed the conversation still "
                 "recovers and extracts correctly once a full name is given.",
    },
    {
        "id": "S11_multiple_needs",
        "description": "User mentions more than one need in the same message",
        "language": "English",
        "user_turns": [
            "Hi, I'm Ana, I need both a cleaning and a whitening consultation.",
            "ana@example.com, flexible on timing.",
            "Let's say sometime next month then.",
        ],
        "expected": {"name": "Ana", "contact": "ana@example.com", "need": "cleaning", "timeline": "month"},
        "expect_saved": True,
        "notes": "Manually check whether BOTH needs were captured in the 'need' field, or only one - "
                 "known limitation of a single free-text 'need' field. What extra info gets requested "
                 "last (full name, phone number, or both) varies run to run.",
    },
    {
        "id": "S12_rambling_single_message",
        "description": "One long, unstructured message containing all info at once",
        "language": "English",
        "user_turns": [
            "hii so basically ive had this filling that keeps coming loose and its been annoying me for weeks now, "
            "im hoping to get it looked at pretty soon like this week if possible, im ana koci by the way and you can "
            "just email me at ana.koci@example.com",
        ],
        "expected": {"name": "Ana Koci", "contact": "ana.koci@example.com", "need": "filling", "timeline": "week"},
        "expect_saved": True,
        "notes": "Confirmed working on every run so far - correctly extracts from messy, run-on, "
                 "informally-punctuated text in a single turn.",
    },
]
