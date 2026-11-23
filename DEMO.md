# Demo script (~2 min, targets a sub-50MB recording)

Recording settings to land under 50MB at ~2 min: 1280×720, 30fps, H.264,
~2,500 kbps video bitrate, mono audio. That's roughly 35–45MB for 2 minutes.
Cut to ~90s (skip the eval section) if you need more headroom.

Have ready before recording:
- The webapp open in a browser tab, sidebar already filled in (host/token/url).
- A fresh `DATABRICKS_TOKEN` (tokens expire in ~1 hour).
- `eval/eval_report.md` open in a second tab/editor for the final beat.

---

## 0:00–0:15 — Hook + problem

> "Federal contract spending data is public — anyone can look it up on
> USAspending.gov. But digging through search filters to answer a real
> question takes time. This is a CSOSA Spending Assistant: ask a plain
> question, get an answer, a chart, and the sources — all from live data,
> read-only, nothing ever written back."

*(Screen: webapp home page, title + caption visible.)*

## 0:15–0:35 — Architecture, fast

> "Under the hood: an MCP server exposes five tools backed by
> USAspending.gov's public API, scoped to CSOSA. An agent loop connects an
> LLM to those tools. Both the MCP server and this web UI are deployed as
> independent Databricks Apps — so this isn't a toy running on my laptop,
> it's live infrastructure."

*(Screen: briefly show the GitHub repo structure — `src/example_server/tools/`,
`agent/`, `webapp/`, `deploy/` — then back to the browser.)*

## 0:35–1:20 — Live demo

> "Let's ask something real."

Type: **"Who are CSOSA's top 5 recipients by total spending?"**
Set budget threshold: **1000000**
Click **Ask**.

> "Watch — tool discovery, then it picks the right tool itself."

*(Let the status block show "Discovered 5 tools" → "called csosa_spending_summary".)*

> "Chart renders first, above the answer. Recipients over my $1M threshold
> turn red automatically — a budget guardrail — and hovering tells you
> exactly who and how much."

*(Hover over a bar, point out the tooltip. Scroll to show the dashed budget line + legend.)*

> "Below that: the narrated answer, and below *that*, the raw source data —
> every award links straight back to its USAspending.gov record. Nothing is
> invented; everything traces back to a citable source."

*(Scroll to the source table, click one "View on USAspending.gov" link if time allows.)*

## 1:20–1:45 — Proof it actually works

> "This isn't just a demo question — there's a 10-question gold-standard
> evaluation harness that runs the full tool-calling loop against the live
> deployed server and grades every answer with an LLM judge."

*(Screen: `eval/eval_report.md` — scroll to the summary line and the token-usage table.)*

> "10 out of 10 correct, and it tracks real cost too — about 11,000 tokens
> per question on average, broken down between the agent actually answering
> and the separate judge grading it."

## 1:45–2:00 — Close

> "Everything here — the server, the agent, this web UI, the eval harness —
> is open on GitHub, deployed live on Databricks right now. Thanks for
> watching."

*(Screen: GitHub repo README, showing the "Live deployment" links table.)*

---

## Cut list if you need to shorten further

Priority order to drop if trimming: (1) architecture beat, (2) clicking a
source link, (3) eval section — in that order. Never cut the live
ask → chart → guardrail → sources sequence; that's the actual proof of the
project.
