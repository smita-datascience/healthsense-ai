# HealthSense AI

A multi-agent health information assistant built around a single question: **how do you make an agentic system's safety claims measurable rather than asserted?**

![Architecture](architecture.png)

---

## What this is

HealthSense AI answers general health questions in plain language — explaining conditions, terminology, and guidance grounded in a curated knowledge base.

It is deliberately **not** a diagnostic tool. It cannot prescribe, dose, or diagnose. That boundary isn't a line in a prompt; it's enforced in code on both sides of the model call.

**Stack:** Python · CrewAI · FastAPI · SQLAlchemy · SQLite · Anthropic Claude

---

## Why safety is the interesting part

Health is a domain where LLM failure modes are asymmetric. A hallucinated dosage, an implied diagnosis, or a missed emergency signal costs far more than an over-cautious refusal.

Most agent projects treat safety as a filter bolted on afterwards. This one is designed around the asymmetry from the start, and then **measured** — because a safety claim you can't falsify isn't a claim.

---

## The safety cascade

Two independent gates, deliberately not sharing a failure mode.

### Gate 1 — input, pre-LLM (`check_input`)

Runs before any model call, in two layers:

**Layer 1: deterministic keyword screen.** Does not block on its own — it *routes*. A keyword hit marks a message as needing scrutiny.

**Layer 2: LLM classifier.** Makes the call, on every message.

**Why Layer 1 routes rather than blocks.** An earlier version blocked on any keyword hit, with a whitelist of "educational" phrasings carved out so that *"what are the warning signs of a heart attack?"* would pass. That scored 0 false alarms on the suite it was built against — and 6 wrong blocks out of 10 on an independently written one. The whitelist had been fitted to the test set that produced it. Whitelists don't generalise; reasoning about intent does.

**What Layer 1 still guarantees.** If Layer 2 can't run — API down, timeout, a silently broken function — a message that hit a keyword is blocked. The deterministic layer is the floor, not the ceiling. The gate never disappears because a service did.

That's the property worth protecting. A model in the safety path can hallucinate, and left alone it **fails open** exactly when you can't afford to lose it. The cheap, certain layer is what stops that.

### Gate 2 — output, post-generation (`check_output`)

Screens the generated answer for specific dosing instructions and diagnostic claims. If it finds either, the answer is **withheld and replaced**, not annotated.

This was a deliberate revision. An earlier version appended a caution below the unsafe text — but a disclaimer under dosing advice still leaves the dosing advice on screen. In an asymmetric-cost domain, withhold.

---

## Evaluation

### Round 1 — red-team suite, 56 cases

```
python -m app.evaluation.run_safety_eval
```

| Gate | Recall | False alarms |
|---|---|---|
| Emergency gate (input) | 25/25 (100%) | 0/11 |
| Output guardrail | 13/13 (100%) | 0/7 |

Adversarial framings included: indirect ("asking for a friend"), fictional ("for a story I'm writing"), minimizing ("probably nothing, but my vision went black"), and hypothetical ("hypothetically, how long can a person go without breathing").

### Round 2 — independent set, 31 cases

```
python -m app.evaluation.run_independent_eval
```

| | Recall | False alarms |
|---|---|---|
| Emergency gate | 21/21 (100%) | 0/10 |

**Why a second set exists.** Round 1 was written alongside the guardrail, which means it can only prove the system handles the cases it was built against. Round 2 was generated from a different starting point — not *"what would evade this code?"* but *"how do people actually write when something is wrong?"* Its cases come from how patients present at triage, how people write to crisis lines, and how fear, embarrassment, and language barriers distort a message: lay somatic description with no clinical vocabulary, apologetic hedging, non-native English, the urgent fact buried after small talk, indirect signals of suicidal intent.

**What it found.** Recall generalised (20/21 on first run). Precision did not — 6 of 10 safe questions were wrongly blocked, exposing the educational whitelist as overfitting. That finding drove the router redesign described above. After the fix: 21/21 recall, 0 false alarms, with Round 1 unchanged.

**Caveat, stated plainly:** Round 2 is *more* independent, not fully independent. Anyone who writes a test set brings their own blind spots. Real independence means someone who has never seen the implementation.

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

## Architecture

Request path:

```
FastAPI → check_input → triage agent → explainer agent (+ BM25 retrieval, memory) → check_output → response
```

**Triage agent** — classifies topic and urgency, decides what a good answer should focus on. Does not answer.

**Explainer agent** — retrieves from the knowledge base, then writes a plain-language answer grounded in what it found.

**Retrieval** — BM25 over a curated health knowledge base. Answers are anchored to source passages rather than parametric memory.

**Memory** — last 3 turns persisted in SQLite via SQLAlchemy, so the crew maintains context across a session.

---

## Setup

```
git clone https://github.com/smita-datascience/healthsense-ai.git
cd healthsense-ai

python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your key:

```
ANTHROPIC_API_KEY=your-key-here
```

Run the API:

```
uvicorn app.main:app --reload
```

---

## Design tradeoffs

Choices made explicitly, not by default.

**CrewAI over LangGraph.** CrewAI's role/task abstraction maps cleanly onto a small, fixed pipeline and got a working vertical slice up fast. LangGraph offers finer control over state and branching, which this system doesn't need yet. If the crew grows conditional or cyclic paths, that flips.

**Sequential over hierarchical process.** The order is known and fixed — triage always precedes explanation. A hierarchical manager agent would add an LLM call and a source of nondeterminism to solve a routing problem that doesn't exist here.

**BM25 over dense embeddings.** Health queries are dense with precise clinical terminology, where lexical match is a strong signal and retrieval is auditable — you can see exactly why a passage was pulled. It also keeps an embedding model and vector store out of the v1 dependency chain. The cost is real; see Limitations.

**RAG over fine-tuning.** The knowledge base changes; the model's behaviour doesn't need to. Grounding gives citable provenance and lets the corpus update without a retraining cycle.

**Deterministic layer first in the cascade.** Covered above — the ordering is the whole argument.

---

## Known limitations

- **Both test sets are still mine.** Round 2 was written from a different angle, but by the same person who wrote the guardrail. Genuinely independent means someone who has never seen the implementation.
- **Layer 2 now runs on every message**, not just the ones Layer 1 missed. More API calls, slightly higher latency and cost. That was the price of dropping the whitelist, and it was worth paying.
- **BM25 misses semantic paraphrase.** "Why does my chest feel tight" won't lexically match a passage on angina. A hybrid retriever (BM25 + dense, rank-fused) is the fix.
- **The knowledge base is curated and small.** Coverage gaps produce refusals rather than wrong answers — the correct failure direction, but still a gap.
- **Memory is session-scoped.** No user profile, no cross-session recall, no semantic memory.
- **No production observability.** No tracing, no live monitoring, no drift detection.
- **I wrote both the guardrail and the red-team set.** That's a blind spot by construction. Independently generated adversarial prompts are the honest next step.

---

## What's next

- A third test set written by someone who has not seen the code
- Cache Layer 2 results for repeated queries, to claw back the cost of routing everything through it
- Hybrid retrieval (BM25 + dense, rank fusion), evaluated against the same golden dataset to prove the complexity earns its place
- Tracing and observability; eval-in-CI so a drop in safety recall fails the build

---

## A note on where the design comes from

Before machine learning, I spent four years writing firmware in C for heavy water plant operations at BARC. In that environment you don't get to say "it's probably fine." You enumerate failure modes, you assume the component fails, and you design so that the failure is survivable.

The cascade in this project is that instinct applied to LLMs: put the layer that cannot fail in front of the layer that can, and then go looking for the cases where you were wrong.