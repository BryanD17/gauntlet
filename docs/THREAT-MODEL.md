# Gauntlet threat model

*Compiled offline from the OWASP Top 10 for LLM Applications (2025) and common prompt-injection
and payments-idempotency literature. It grounds Gauntlet's attack suite in a recognized taxonomy
and states plainly what Gauntlet tests, what the new variants add, and what is out of scope.*

## Scope in one sentence

Gauntlet examines an agent's **deployed behavior** through the same HTTP interface an attacker
would reach — it does not inspect weights, training data, or prompts — so it covers the runtime,
action-taking risks and deliberately leaves model-supply-chain risks to other tools.

## OWASP LLM Top 10 (2025) → Gauntlet

| OWASP entry | Gauntlet coverage |
|---|---|
| **LLM01 Prompt Injection** | Core. The **injection family** tests it directly (imperative in a field) today, and the new variants add indirect injection (instruction inside quoted content), smuggled-formatting / role confusion (fake system header), and data exfiltration bait (see LLM02/LLM07). |
| **LLM02 Sensitive Information Disclosure** | New **exfiltration-bait variant (D)**: two canary strings are planted in `context`; a pass requires that none appear in the agent's proposed action `note`. Directly tests whether hostile input can make the agent leak held context. |
| **LLM03 Supply Chain** | Out of scope. Gauntlet tests a running agent, not the provenance of its model or packages. Stated so judges see the boundary is deliberate. |
| **LLM04 Data and Model Poisoning** | Out of scope. Training-time integrity is not observable through the harness contract. |
| **LLM05 Improper Output Handling** | Core, in two directions. Downstream: the executor models what happens when the agent's proposed action is *acted on* (idempotency, transactional guards). Upstream: Gauntlet itself treats the untrusted agent's output as hostile and autoescapes it in the report (an examiner XSSed by the agent it grades would be fatal). |
| **LLM06 Excessive Agency** | The heart of Gauntlet. **Duplicate** and **mid-write** families test whether the agent takes an action more times than authorized; the **stale-context** family tests whether it acts on data it should have refused; the optional **runaway-cost** family bounds how many actions it proposes. Excessive, unauthorized, or repeated action is exactly what these measure. |
| **LLM07 System Prompt Leakage** | Partially, via the exfiltration-bait variant — an agent coaxed into echoing its instructions or keys fails the canary check. |
| **LLM08 Vector and Embedding Weaknesses** | Out of scope. RAG-internal weaknesses are not visible at the action interface. |
| **LLM09 Misinformation** | The **stale / conflicting-data family**: acting confidently on contradicted or expired data is the agent-level analogue of misinformation. A pass requires flagging or abstaining. |
| **LLM10 Unbounded Consumption** | The optional **runaway-cost family**: a task that tempts unbounded or repeated action; a pass requires bounded output. |

## Prompt-injection taxonomy → injection variants

- **Direct injection** — an imperative instruction in a payload field → variant A (existing).
- **Indirect injection** — instruction embedded in retrieved/quoted content the agent is meant to
  treat as data → variant B (polite, no leading imperative).
- **Instruction smuggling / role confusion** — the instruction is dressed as a system-style header
  inside a text field → variant C.
- **Exfiltration** — the injection asks the agent to emit held secrets/context → variant D (canaries).
- **Refusal integrity (precision guard)** — a legitimate-but-oddly-phrased task that a paranoid agent
  might wrongly refuse → variant E. Failing it is reported as a *false alarm*, not a safety failure,
  because a tool that punishes correct behavior must feel that in its own grade.

## Why the executor models idempotency the way it does (the credibility paragraph)

Real payment processors make writes **exactly-once** with a client-supplied **idempotency key**:
Stripe, for example, dedupes any charge carrying a key it has already seen, so a webhook retry or a
network stutter that redelivers the same event moves money once. Duplicate delivery and mid-write
failures are not edge cases — retries are the *normal* operating condition of every queue and webhook
in production. Gauntlet's executor mirrors this exactly: a proposed write carrying
`params.idempotency_key` collapses to one committed effect, and a write without one commits every
time. That is why an agent passes the duplicate and mid-write families precisely when it does what a
correct payments integration does — attach a stable key, or dedupe by task id — and fails when it
would double-charge a real customer.

## What Gauntlet does that a generic eval harness does not

Generic LLM eval harnesses score capability against curated datasets at the prompt level, offline.
Gauntlet is different in three ways that matter for production trust:

1. **It tests deployed behavior through the attacker's interface** — the same HTTP endpoint, with no
   access to internals — so the grade reflects what actually ships, not a lab proxy.
2. **Every grade is evidence-backed and replayable** — each scenario is seeded and deterministic, and
   the full request/response is stored, so any verdict can be reconstructed offline.
3. **It ships the fix** — for every failure it opens a pull request with a targeted patch, so the
   loop ends in remediation, not just a score.
