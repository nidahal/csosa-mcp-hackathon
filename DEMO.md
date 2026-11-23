# Demo script (~2:30, targets a sub-50MB recording)

Recording settings to land under 50MB at ~2:30: 1280×720, 30fps, H.264,
~2,200 kbps video bitrate, mono audio. Drop to ~2 min (see cut list) if you
need more headroom.

Have ready before recording:
- The webapp open in a browser tab.
- A fresh `DATABRICKS_TOKEN` (tokens expire in ~1 hour) — host and MCP server
  URL are pre-filled now, so this is the only sidebar field you need to fill.
- The GitHub repo README open in a second tab, scrolled to the architecture
  diagram.
- `eval/eval_report.md` open in a third tab/editor for the proof beat.

---

## 0:00–0:15 — Hook + problem

> "Federal contract spending data is public — anyone can look it up on
> USAspending.gov. But digging through search filters to answer a real
> question takes time. This is a CSOSA Spending Assistant: have a
> conversation about CSOSA's spending and get answers, charts, and sources —
> all from live data, read-only, nothing ever written back."

*(Screen: webapp home page, title + caption visible.)*

## 0:15–0:30 — Architecture, fast

> "Under the hood: an MCP server exposes five tools backed by
> USAspending.gov's public API, scoped to CSOSA. One shared agent loop
> connects an LLM to those tools — this web UI, a CLI agent, and the eval
> harness are all just clients of that same loop. Both the MCP server and
> this web UI are deployed as independent Databricks Apps — live
> infrastructure, not a laptop demo."

*(Screen: GitHub README's architecture diagram — point at the two Databricks
App boxes and the shared agent/core.py box.)*

## 0:30–1:30 — Live demo: ask, then follow up

> "Let's ask something real."

Type in the chat box: **"Who are CSOSA's top 5 recipients by total spending?"**
Set budget threshold in the sidebar: **1000000**, press Enter again if needed.

> "Watch — tool discovery, then it picks the right tool itself."

*(Let the status block show "Discovered 5 tools" → "called csosa_spending_summary".)*

> "Chart renders first, above the answer. Recipients over my $1M threshold
> turn red automatically — a budget guardrail — and hovering names exactly
> who and how much."

*(Hover over a bar, point out the tooltip. Scroll to show the dashed budget line + legend.)*

> "Below that: the narrated answer, and below *that*, the raw source data —
> every award links straight back to its USAspending.gov record."

Now type a follow-up in the **same chat box**: **"What's the combined total of those five?"**

> "This is a real conversation — it's answering from what it already
> retrieved, no second tool call needed, because it remembers the context."

*(Point out: no new "Discovered tools" status, no new chart — just a direct answer.)*

## 1:30–2:00 — Proof it actually works

> "This isn't just a demo question — there's a 14-question gold-standard
> evaluation harness that runs the full tool-calling loop against the live
> deployed server and grades every answer with an LLM judge."

*(Screen: `eval/eval_report.md` — scroll to the summary line, the tool-usage
table, and the token-usage table.)*

> "14 out of 14 correct, and it tracks real cost too — about 12,000 tokens
> per question on average, broken down between the agent actually answering
> and the separate judge grading it."

## 2:00–2:15 — Close

> "Everything here — the server, the agent, this web UI, the eval harness —
> is open on GitHub, deployed live on Databricks right now. Thanks for
> watching."

*(Screen: GitHub repo README, showing the "Live deployment" links table.)*

---

## Cut list if you need to shorten further

Priority order to drop if trimming: (1) architecture diagram beat, (2) the
follow-up/multi-turn beat, (3) eval section — in that order. Never cut the
live ask → chart → guardrail → sources sequence; that's the actual proof of
the project. Dropping all three optional beats gets you back to the
original ~2:00 cut.
