# Testing: channels

Covers WhatsApp, voice calls, Android companion.

## WhatsApp

### Must test

| Case | Level | Autonomous check |
| --- | --- | --- |
| Allowlisted text turn processed | I/E | outbound/logic trace exists |
| Non-allowlisted ignored | C | zero tool calls / side effects |
| Voice note → STT → same as text intent | I/E | fixture transcript match + reminder/todo effect |
| Empty/garbage STT | I | clarification outbound; no hard action |
| TTS only when inbound was audio (policy) | C/I | TTS spy call count |

### Skip / defer

- Real multi-device WhatsApp Web QR flakiness in CI (live-smoke only)
- Subjective “friendly tone” (eval lane)

### Harness needs

Inbound injector, outbound catcher, audio fixtures.

## Voice calls

### Must test

| Case | Level | Autonomous check |
| --- | --- | --- |
| Outbound call on escalation policy | I/E | mock provider `createCall` once |
| Tool allowlist excludes buy/book/self-mod-apply | C | attempted forbidden tool rejected |
| After-call summary message | I | WhatsApp catcher has summary |
| Quiet hours suppress call | U/I | fake clock inside quiet window → no call |

### Skip / defer

- Real PSTN audio quality
- Full realtime barge-in UX (later soak)

## Android companion

### Must test

| Case | Level | Autonomous check |
| --- | --- | --- |
| Todo projection sync | I/E | state equality WhatsApp-created ↔ Android API |
| Approval card fields present | I | payload has summary/expiry/type |
| Accept executes once | C/E | adapter execute count 0→1 |
| Deny never executes | C/E | execute stays 0 |
| Self-mod approval shows diff metadata | I | files_touched + rollback_ref present |
| Kill-switch status visible | I | status flags in API |

### Approach

Prefer **API-level** Android node simulation over emulator UI for autonomy. Add screenshot diffs only if the companion UI is custom and flaky-prone UI is worth it.

### Skip / defer

- Full Play Store install path
- Push notification OEM quirks (spot-check live)
