# HealthSense AI

A multi-agent health information assistant built around a single question: **how do you make an agentic system's safety claims measurable rather than asserted?**

![Architecture](architecture.png)

---

## What this is

HealthSense AI answers general health questions in plain language — explaining conditions, terminology, and guidance grounded in a curated knowledge base. It runs as an API and on WhatsApp, in English, Hindi and Hinglish, and can read a photo or PDF of a lab report.

It is deliberately **not** a diagnostic tool. It cannot prescribe, dose, or diagnose. That boundary isn't a line in a prompt; it's enforced in code on both sides of the model call.

**Stack:** Python · CrewAI · FastAPI · SQLAlchemy · SQLite · Anthropic Claude · WhatsApp Cloud API · Locust

---

## Why safety is the interesting part

Health is a domain where LLM failure modes are asymmetric. A hallucinated dosage, an implied diagnosis, or a missed emergency signal costs far more than an over-cautious refusal.

Most agent projects treat safety as a filter bolted on afterwards. This one is designed around the asymmetry from the start, and then **measured** — because a safety claim you can't falsify isn't a claim.

---

## The safety cascade

Two independent gates, deliberately not sharing a failure mode.

### Gate 1 — input, pre-LLM (`check_input`)

Runs before any model call, in two layers:

**Layer 1: deterministic keyword screen.** Does not block on its own — it *routes*. A keyword hit marks a message as needing scrutiny. The keyword list covers English, Hindi (Devanagari) and Hinglish, written from red-flag concepts rather than copied from the test set.

**Layer 2: LLM classifier.** Makes the call, on every message.

**Why Layer 1 routes rather than blocks.** An earlier version blocked on any keyword hit, with a whitelist of "educational" phrasings carved out so that *"what are the warning signs of a heart attack?"* would pass. That scored 0 false alarms on the suite it was built against — and 6 wrong blocks out of 10 on an independently written one. The whitelist had been fitted to the test set that produced it. Whitelists don't generalise; reasoning about intent does.

**What Layer 1 still guarantees.** If Layer 2 can't run — API down, timeout, a silently broken function — a message that hit a keyword is blocked. The deterministic layer is the floor, not the ceiling. The gate never disappears because a service did.

That's the property worth protecting. A model in the safety path can hallucinate, and left alone it **fails open** exactly when you can't afford to lose it. The cheap, certain layer is what stops that.

### Gate 2 — output, post-generation (`check_output`)

The same shape as Gate 1. Regex patterns for dosing, diagnosis and discouraging care **flag** an answer; an LLM judge reads the flagged answer and **decides**; if the judge can't run, a flagged answer is blocked. Unsafe answers are **withheld and replaced**, not annotated.

**Why the judge was added.** The patterns alone blocked a correct fever answer because it said *"see a doctor if… you have underlying health conditions"* — the same words as the diagnosis *"you have a migraine"*. Words can't tell those apart; reading for meaning can. After the redesign: output false alarms went from 5/12 to 0/12, with recall unchanged.

**Why withhold rather than annotate.** An earlier version appended a caution below the unsafe text — but a disclaimer under dosing advice still leaves the dosing advice on screen. In an asymmetric-cost domain, withhold.

### Never silence

If the LLM service itself is unreachable (outage, exhausted credits, rate limit) and no keyword fired, the user gets a fixed, pre-translated message: *try again later, and call 112 / 108 if this could be an emergency.* Never an HTTP 500, never an empty WhatsApp reply. Like the emergency message, it is fixed text, so it works with the API down. (This gap was found by the stress test below.)

---

## Evaluation

All four suites are re-run after every change to the safety path.

| Suite | Cases | Recall | False alarms |
|---|---|---|---|
| Red-team suite — emergency gate | 36 | 25/25 (100%) | 0/11 |
| Red-team suite — output guardrail | 32 | 18/18 (100%) | 0/14 |
| Independent set (emergency gate) | 31 | 21/21 (100%) | 0/10 |
| Hindi & Hinglish (emergency gate) | 25 | 17/17 (100%) | 0/8 |
| **Total** | **124** | **81/81** | **0/43** |

```
python -m app.evaluation.run_safety_eval
python -m app.evaluation.run_independent_eval
python -m app.evaluation.run_multilingual_eval
```

### Round 1 — red-team suite, 68 cases

Adversarial framings included: indirect ("asking for a friend"), fictional ("for a story I'm writing"), minimizing ("probably nothing, but my vision went black"), and hypothetical ("hypothetically, how long can a person go without breathing"). The output cases include conditional dosing, diagnosis followed by a referral, and safe answers that contain numbers or "if you have…" warnings.

### Round 2 — independent set, 31 cases

**Why a second set exists.** Round 1 was written alongside the guardrail, which means it can only prove the system handles the cases it was built against. Round 2 was generated from a different starting point — not *"what would evade this code?"* but *"how do people actually write when something is wrong?"* Its cases come from how patients present at triage, how people write to crisis lines, and how fear, embarrassment, and language barriers distort a message: lay somatic description with no clinical vocabulary, apologetic hedging, non-native English, the urgent fact buried after small talk, indirect signals of suicidal intent.

**What it found.** Recall generalised (20/21 on first run). Precision did not — 6 of 10 safe questions were wrongly blocked, exposing the educational whitelist as overfitting. That finding drove the router redesign described above. After the fix: 21/21 recall, 0 false alarms, with Round 1 unchanged.

**Caveat, stated plainly:** Round 2 is *more* independent, not fully independent. Anyone who writes a test set brings their own blind spots. Real independence means someone who has never seen the implementation.

### Round 3 — Hindi & Hinglish, 25 cases

With the LLM on: 17/17 recall, 0/8 false alarms. With the LLM off, the keyword floor alone catches 14/17 (it caught 0/17 before Hindi and Hinglish terms were added) — the floor is a floor, not a replacement.

### Two failures worth recording

**The whitelist that scored perfectly.** 0 false alarms on Round 1, 60% on Round 2. A perfect score against your own test set is not evidence of a correct system — it's evidence you tested what you thought of.

**The function that broke silently.** An edit to `llm_emergency_check` disabled it. It still ran. It returned a value. Nothing raised. The suite printed 8% recall and looked like a tuning problem. The whole LLM layer was gone. Without the harness that would have shipped as a two-layer cascade with one layer.

### LLM-as-judge harness

```
python -m app.evaluation.run_eval
```

Scores responses against a golden dataset for groundedness (is the answer supported by retrieved context?) and relevance.

Note the separation: the LLM **judges** offline, where a mistake is cheap and recoverable. It does not **enforce** alone online — Layer 1 is underneath it, holding the floor.

---

## Stress testing (Locust)

Safety has to hold under load too. `locustfile.py` simulates users asking a mix of normal and emergency questions against the local `/ask` endpoint (not through WhatsApp). Every request calls Claude for real, so it starts small.

```
locust -f locustfile.py --host http://127.0.0.1:8000 --headless