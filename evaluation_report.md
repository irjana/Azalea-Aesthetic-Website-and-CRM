# Chatbot Evaluation Results

Generated: 2026-08-31 19:41

- Scenarios run: 12
- Completed with expected save/no-save outcome: 11/12
- Scenarios that needed the catch-all fallback message: 3/12
- Auto-checkable field extraction accuracy: 86.7% (39/45 fields)

Fields marked REVIEW were intentionally excluded from automated scoring (free-text fields like `need`/`timeline` where paraphrasing is expected and acceptable) - these require a quick manual read of the transcript, included below.

A scenario using the catch-all fallback means the bot asked for something beyond what the scripted turns provided (e.g. a second contact method, a fuller name, a firmer timeline) - the harness then restated all expected info in one message so the scenario could still complete. This is expected given observed run-to-run variance in the model's behavior, not a scripting error.

## Per-scenario results

| ID | Description | Saved as expected | Turns | Fallback used | Fields (pass/fail/review) |
|---|---|---|---|---|---|
| S1_all_info_upfront | All four fields given in a single opening message | yes | 2 | no | 4 / 0 / 0 |
| S2_gradual_info | Info volunteered gradually across several turns | yes | 5 | no | 4 / 0 / 0 |
| S3_vague_timeline | User gives a vague, non-specific timeline | yes | 3 | no | 3 / 1 / 0 |
| S4_one_refusal_then_given | User initially declines contact info, then provides it | yes | 4 | no | 4 / 0 / 0 |
| S5_two_refusals_declined | User refuses contact info twice - should end with contact='declined' | yes | 3 | no | 2 / 1 / 1 |
| S6_offtopic_as_need | Off-topic content given as the answer to the 'need' question | NO | 5 | yes | 0 / 4 / 0 |
| S7_offtopic_mid_flow | Off-topic content given later, as the answer to a different pending question | yes | 3 | no | 4 / 0 / 0 |
| S8_borderline_not_offtopic | A question that sounds tangential but is legitimately dental-related - guardrail should NOT block it | yes | 4 | yes | 4 / 0 / 0 |
| S9_italian_full_conversation | Full conversation conducted in Italian | yes | 3 | no | 2 / 0 / 2 |
| S10_informal_name_then_full_name | User gives a nickname first; bot asks for a full name (accepted behavior) and receives one | yes | 3 | no | 4 / 0 / 0 |
| S11_multiple_needs | User mentions more than one need in the same message | yes | 4 | yes | 4 / 0 / 0 |
| S12_rambling_single_message | One long, unstructured message containing all info at once | yes | 1 | no | 4 / 0 / 0 |

## Notes for manual review

**S1_all_info_upfront** - Should not ask redundant questions beyond confirming/collecting a second contact method and the name format. KNOWN BEHAVIOR: the bot inconsistently asks whether a single first name is 'complete' - accepted, not treated as a bug.
  Extracted: `{'name': 'Dritan', 'contact': 'dritan@example.com, +355691112222', 'need': 'Cleaning and checkup', 'timeline': 'Within the next month'}`

**S2_gradual_info** - KNOWN BEHAVIOR (not treated as a bug per project decision): the bot re-asks about the need after every subsequent turn instead of accepting 'tooth pain' on its own, sometimes resolving after 1-2 extra turns and sometimes taking longer.
  Extracted: `{'name': 'Elira', 'contact': 'elira@example.com', 'need': 'General tooth pain consultation', 'timeline': 'Next two weeks'}`

**S3_vague_timeline** - KNOWN BEHAVIOR: the bot does not always accept a vague timeline or a given email as final on the first pass, and re-confirms details - same underlying pattern as S2/S10 (wanting a more complete/confirmed answer). Accepted, not a bug.
  Extracted: `{'name': 'Marco', 'contact': 'marco@example.com', 'need': 'Teeth whitening', 'timeline': 'Sometime this year'}`
  Failed fields: timeline (expected 'month', got 'Sometime this year')

**S4_one_refusal_then_given** - Confirms recovering from a single refusal still ends with real contact info, not 'declined'.
  Extracted: `{'name': 'Sara', 'contact': 'sara@example.com', 'need': 'Root canal consultation', 'timeline': 'Next week'}`

**S5_two_refusals_declined** - DOCUMENTED KNOWN LIMITATION, intentionally left unfixed per project decision: count_contact_refusals() in main.py only counts a refusal when the assistant's PRECEDING message asked about contact - it does not read the content of the user's reply, so ordering variance can cause a real refusal to go uncounted. Separately, even on runs where the refusal count IS detected correctly, the model has been observed saying it will save the lead without actually invoking save_lead - a second, independent instruction-following gap. Record the actual outcome each run; cite both as limitations in the results/limitations chapter. No fallback message is sent for this scenario (see run_eval.py) since restating contact info would defeat the point of testing the decline path.
  Extracted: `{'name': 'Blerta', 'contact': 'Not provided', 'need': 'Braces for teeth straightening', 'timeline': 'Not specified'}`
  Failed fields: contact (expected 'declined', got 'Not provided')

**S6_offtopic_as_need** - The off-topic redirect itself has been confirmed working correctly on every run so far - first reply always redirects instead of treating house-building as the need. Completion timing on the 'need' field varies run to run (see S2 notes).
  Failed fields: name (expected 'Laura', got 'None'); contact (expected 'laura@example.com', got 'None'); need (expected 'cleaning', got 'None'); timeline (expected 'week', got 'None')

**S7_offtopic_mid_flow** - Confirmed working on every run so far - correctly redirects and re-asks the pending question instead of absorbing the off-topic remark.
  Extracted: `{'name': 'Laura', 'contact': 'laura@example.com', 'need': 'cleaning', 'timeline': 'sometime next month'}`

**S8_borderline_not_offtopic** - IMPORTANT: confirms the guardrail isn't over-triggering on legitimate dental-adjacent questions (insurance, hours, pricing) - confirmed not blocked on every run so far. What additional info it asks for last (phone vs. full name) varies run to run.
  Extracted: `{'name': 'Enkel', 'contact': 'enkel@example.com', 'need': 'Checkup', 'timeline': 'This month'}`

**S9_italian_full_conversation** - Confirmed working on every run so far - stays in Italian throughout the whole conversation, not just the final message.
  Extracted: `{'name': 'Marco', 'contact': 'marco.it@example.com', 'need': 'Pulizia dentale', 'timeline': 'Entro un mese'}`

**S10_informal_name_then_full_name** - KNOWN BEHAVIOR (not treated as a bug per project decision): the bot requires a full name and does not accept a nickname on its own. Confirmed the conversation still recovers and extracts correctly once a full name is given.
  Extracted: `{'name': 'Jonida Krasniqi', 'contact': 'j@example.com', 'need': 'Filling replacement', 'timeline': 'Next few weeks'}`

**S11_multiple_needs** - Manually check whether BOTH needs were captured in the 'need' field, or only one - known limitation of a single free-text 'need' field. What extra info gets requested last (full name, phone number, or both) varies run to run.
  Extracted: `{'name': 'Ana', 'contact': 'ana@example.com', 'need': 'cleaning and whitening consultation', 'timeline': 'next month'}`

**S12_rambling_single_message** - Confirmed working on every run so far - correctly extracts from messy, run-on, informally-punctuated text in a single turn.
  Extracted: `{'name': 'Ana Koci', 'contact': 'ana.koci@example.com', 'need': 'Loose filling examination and repair', 'timeline': 'This week'}`
