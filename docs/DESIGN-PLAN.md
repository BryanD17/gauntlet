# Gauntlet web console — design plan

The governing idea: **the page is an examination in progress.** Gauntlet is a certification
authority that attacks agents, so the visual world is examination, evidence, verdict, and seal —
not generic SaaS. The hero does not describe the product; it *performs* it: four attacks resolve,
live, into a struck grade. Evidence is shown, never asserted.

## The principle that makes this not a default page

Most generated pages *describe* with cards. Gauntlet *adjudicates*. The single characteristic
moment — the four attacks resolving into a letter grade — opens the landing page as a compact
live-looking panel and *is the same component* the console shows for a real run. One idea, built
once, shown twice. The grade letter is a display element with the weight of a stamped seal, not
large body text. Everything else is quiet so that moment carries.

## Palette (deliberate, tied to meaning — not one acid accent)

The expressive core is the three **verdict colors**, because in this world color *means* the
outcome. They are the palette, not decoration.

- `--ink: #0E0F12` — near-black ground, the examination hall.
- `--panel: #16181D` — raised surface for evidence plates.
- `--paper: #EDEAE3` — warm off-white primary text (the paper a certificate is printed on).
- `--muted: #8A8F98` — secondary text.
- `--pass: #3ECF8E` / `--fail: #E5484D` / `--abstain: #E0A63E` — verdict green / red / amber.
- `--seal: #5B8DEF` — the single cool accent, used only for the seal/wordmark mark and primary action, never for body links.
- `--hair: #26282E` — 1px hairline borders (plate edges).

## Typography (each face earns its role)

- **Space Grotesk 700** — the grade letter and page headlines only. The grade letter is set at
  display size (clamp ~96–180px) with tight tracking, as a struck seal.
- **Inter 400/500/600** — all body and UI. Sentence case. A real scale: 13 / 15 / 18 / 24 / 40.
- **JetBrains Mono 400** — *only* inside evidence blocks and the harness code sample. Never
  sprinkled for flavor, never for eyebrows or labels.

No tracked-out all-caps eyebrow stacked over every heading. No meta strings joined by middle dots.
No arrow glued to every link (links are underlined on hover; the primary CTA is a button that says
what it does). Cards are evidence plates with a hairline and a colored left rule by verdict — not
identical soft-shadow rounded boxes.

## Motion

One orchestrated moment: attacks resolve in sequence (each plate settles as its verdict lands),
then the grade letter strikes in. 200ms ease-out per plate, a slightly firmer entrance for the
grade. Everything else is still. `prefers-reduced-motion` renders the final state with no motion.

## Landing `/` — layout

```
┌───────────────────────────────────────────────────────────┐
│  GAUNTLET·seal                              Console  Board │
│                                                            │
│   Certification for AI agents.                             │
│   Grade any agent the way an attacker would, before        │
│   it ships.                        [ Run an examination ]  │
│                                                            │
│     ┌─ live examination panel ───────────────────┐        │
│     │  Prompt injection      ▐ PASS               │        │
│     │  Duplicate delivery    ▐ PASS      →   [ A ]│        │
│     │  Mid-write failure     ▐ PASS               │        │
│     │  Stale data            ▐ ABSTAIN            │        │
│     └──────────────────────────────────────────────┘      │
│                                                            │
│   How it works — 3 steps, with real report/console shots   │
│   [ point ]        [ attack ]         [ grade + fix PR ]   │
│                                                            │
│   Live examples:  [ Naive · F ]     [ Hardened · A ]       │
│   Get your agent certified — 20-line wrapper + links       │
│   Footer: hackathon · leaderboard · grading vN             │
└───────────────────────────────────────────────────────────┘
```

## Run console `/console` — layout

```
┌───────────────────────────────────────────────────────────┐
│  GAUNTLET·seal                              Console  Board │
│                                                            │
│   Run an examination                                       │
│   ┌ form ─────────────────────────────────────────────┐   │
│   │ Agent /task URL   [___________________________]    │   │
│   │ GitHub repo (opt) [___________________________]    │   │
│   │ Team name         [___________________________]    │   │
│   │ [ ] allow remote host   [ ] no-fix (keep source)   │   │
│   │            [ Run examination ]  [ Try reference ]  │   │
│   └────────────────────────────────────────────────────┘  │
│                                                            │
│   ┌ examination (streams live) ───────────────┐  [ grade ]│
│   │ Prompt injection    ▐ …→ PASS   evidence   │   strikes │
│   │ Duplicate delivery  ▐ …→ PASS   evidence   │   in when │
│   │ Mid-write failure   ▐ …→ PASS   evidence   │   done    │
│   │ Stale data          ▐ …→ ABSTAIN evidence  │  caught/  │
│   └─────────────────────────────────────────────┘ landed/…│
│   result links: report · PRs · Linear · leaderboard        │
└───────────────────────────────────────────────────────────┘
```

## Leaderboard `/leaderboard`

The existing ranked table, served live from `leaderboard.json`: rank, team, grade (verdict-colored),
score, attacks survived, report link. Rank-1 row emphasized, subtle row hover. No search/filter/pager.

## Quality floor (met, not announced)

Responsive to phone width (form and panels stack; the live panel scrolls within its plate).
Visible keyboard focus (2px `--seal` outline). Accessible contrast on all text. Reduced-motion honored.
Every page renders complete with no Higgsfield asset present; assets only enhance.
