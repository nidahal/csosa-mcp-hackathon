# CSOSA MCP Server — Gold Question Evaluation Report

Model: `databricks-claude-sonnet-4-5`  |  Questions: 10  |  Accuracy: 10/10 (100%)
Average tool calls per question: 1.6  |  Average rounds per question: 2.6  |  Average tokens per question: 11,648

## Interpretation

**Final result: 10/10 (100%) on the second run.** The first run (not shown above —
superseded) scored 7/10, but all 3 failures traced back to an error in how the
*gold answers* were constructed, not a tool-usage failure by the agent:

- **Finding 1 — `fiscal_year` on `csosa_search_contract_awards` filters by action
  date, not by "did the award belong to this year."** Q7–Q9 originally assumed
  CSOSA's "FY2023 top award" was a $14.2M award to Bradley Technologies (which
  I'd seen earlier as the #3 all-time-largest award and wrongly assumed was also
  the FY2023-filtered #1). It isn't. Filtering `fiscal_year=2023` actually
  surfaces an $18.1M award to Omniplex World Services — a contract originally
  signed in 2018 that had a modification action dated within FY2023 — ranked by
  its **total** award value, not value obligated specifically in FY2023. The
  agent called the tool correctly and reported the true data (6 offers, NAICS
  541330) both times; my hand-written expected answers were stale. I fixed the
  gold file to match verified live data and re-ran — all 3 then passed. This is
  worth fixing in the tool's docstring: `fiscal_year` currently reads as "award
  belongs to this federal fiscal year," but it really means "award had
  reportable activity during this fiscal year, sorted by lifetime award value."
  A model (or a human) can easily make the same wrong assumption I did.

- **Finding 2 — IDV child-award lists can be small and mixed-agency, which is
  exactly as designed, but surprised the agent on the first run.** For Q9, the
  agent correctly noticed only one DoD order existed under the IDV instead of
  the two my original question assumed — it didn't hallucinate a second one,
  it flagged the discrepancy and still extracted the one real DoD award ID.
  That's good failure behavior: the tool's "not scoped to CSOSA" docstring note
  (added when the tool was built) meant the agent reasoned about the mismatch
  instead of guessing. After I corrected the question to ask about the Federal
  Communications Commission's orders on that IDV (which genuinely has three),
  the agent paged through all 10 children, filtered correctly, and sorted to
  find the smallest — a clean 3-tool-call chain (search → details → IDV
  children).

- **Finding 3 — tool usage skewed toward the core 3 tools; the 2 new ones
  (`csosa_search_subawards`, `csosa_list_idv_child_awards`) were each exercised
  exactly once.** That matches their narrower real-world use (most questions
  about federal spending are about prime awards), but it also means this
  10-question set gives weak signal on those two tools specifically — a larger
  eval batch should deliberately weight toward sub-award and IDV-chain
  questions if the goal is confidence in those two newer tools specifically.

- No question needed anywhere close to `MAX_TOOL_ROUNDS` (8) or many pages of
  results — average 1.6 tool calls and 2.6 rounds per question. The agent
  resolved every multi-hop chain in the minimum number of calls (search →
  details → [IDV children]), with no backtracking or redundant calls observed
  in any trace.

- **Token usage (added on a later re-run):** ~113.6k tokens went to the agent
  answering all 10 questions (~11.4k average, mostly prompt tokens from the
  tool-calling loop's system prompt + accumulating tool results) and ~2.9k to
  the LLM judge grading them — judging costs roughly 2.5% of what answering
  does, as expected for a short one-shot grading prompt versus a multi-round
  tool-calling loop.

## Token usage across all questions

Counts come from the `usage` field each serving-endpoint response returns; 0 for any endpoint that doesn't report it. "Agent" is answering the question (all tool-calling rounds); "Judge" is the separate LLM-as-judge grading call.

| | Prompt tokens | Completion tokens | Total |
|---|---|---|---|
| Agent | 110,572 | 3,054 | 113,626 |
| Judge | 2,457 | 401 | 2,858 |
| **Total** | **113,029** | **3,455** | **116,484** |

## Tool usage across all questions

| Tool | Calls |
|---|---|
| `csosa_search_contract_awards` | 5 |
| `csosa_get_award_details` | 5 |
| `csosa_spending_summary` | 4 |
| `csosa_list_idv_child_awards` | 1 |
| `csosa_search_subawards` | 1 |

## Per-question results

### Q1. ✅ PASS

**Question:** Considering only federal fiscal years 2008 through 2020 (inclusive), how many of those fiscal years had total CSOSA contract obligations exceeding $45,000,000?

**Expected:** 4

**Actual:** Now let me count how many fiscal years had obligations exceeding $45,000,000:

- 2008: $23,484,312.23 - No
- 2009: $28,280,049.82 - No
- 2010: $65,756,123.35 - **Yes**
- 2011: $25,805,339.69 - No
- 2012: $20,073,863.52 - No
- 2013: $27,880,154.09 - No
- 2014: $48,897,689.94 - **Yes**
- 2015: $43,523,901.90 - No
- 2016: $43,801,044.18 - No
- 2017: $57,696,404.42 - **Yes**
- 2018: $49,486,511.32 - **Yes**
- 2019: $44,088,045.65 - No
- 2020: $41,120,129.05 - No

**4 fiscal years** (2010, 2014, 2017, and 2018) had total CSOSA contract obligations exceeding $45,000,000.

**Judge reason:** The agent correctly identified 4 fiscal years (2010, 2014, 2017, and 2018) with obligations exceeding $45,000,000, matching the expected answer.

**Rounds:** 2  |  **Tool calls:** 1

**Tokens:** agent 8,416 (prompt 7,977 / completion 439)  |  judge 503  |  **total 8,919**

<details><summary>Tool call trace</summary>

1. `csosa_spending_summary({"group_by": "fiscal_year", "start_date": "2007-10-01", "end_date": "2020-09-30"})`

</details>

### Q2. ✅ PASS

**Question:** Considering only federal fiscal years 2008 through 2020 (inclusive), which single fiscal year had the highest total CSOSA contract obligations? Answer with the 4-digit fiscal year.

**Expected:** 2010

**Actual:** Based on the data, fiscal year **2010** had the highest total CSOSA contract obligations with $65,756,123.35.

**2010**

**Judge reason:** The agent correctly identified 2010 as the fiscal year with the highest total CSOSA contract obligations.

**Rounds:** 2  |  **Tool calls:** 1

**Tokens:** agent 8,137 (prompt 7,966 / completion 171)  |  judge 233  |  **total 8,370**

<details><summary>Tool call trace</summary>

1. `csosa_spending_summary({"group_by": "fiscal_year", "start_date": "2007-10-01", "end_date": "2020-09-30"})`

</details>

### Q3. ✅ PASS

**Question:** Considering only federal fiscal years 2008 through 2020 (inclusive), which recipient received the highest total obligated amount from CSOSA prime contracts? Give the recipient's name exactly as it appears in USAspending.gov records.

**Expected:** IPI GRAMMTECH LTD

**Actual:** **IPI GRAMMTECH LTD**

**Judge reason:** The agent's answer "IPI GRAMMTECH LTD" matches the expected answer exactly, despite being formatted in bold.

**Rounds:** 2  |  **Tool calls:** 1

**Tokens:** agent 7,998 (prompt 7,837 / completion 161)  |  judge 230  |  **total 8,228**

<details><summary>Tool call trace</summary>

1. `csosa_spending_summary({"group_by": "recipient", "start_date": "2007-10-01", "end_date": "2020-09-30", "limit": 1})`

</details>

### Q4. ✅ PASS

**Question:** Considering only federal fiscal years 2008 through 2020 (inclusive), which Product or Service Code category received the highest total CSOSA contract obligations?

**Expected:** SOCIAL- SOCIAL REHABILITATION

**Actual:** **SOCIAL- SOCIAL REHABILITATION** received the highest total CSOSA contract obligations during federal fiscal years 2008-2020, with **$68,103,288.60** in total obligations.

**Judge reason:** The agent correctly identified "SOCIAL- SOCIAL REHABILITATION" as the Product or Service Code category with the highest total CSOSA contract obligations for fiscal years 2008-2020.

**Rounds:** 2  |  **Tool calls:** 1

**Tokens:** agent 8,202 (prompt 7,997 / completion 205)  |  judge 255  |  **total 8,457**

<details><summary>Tool call trace</summary>

1. `csosa_spending_summary({"group_by": "product_or_service", "start_date": "2007-10-01", "end_date": "2020-09-30", "limit": 10})`

</details>

### Q5. ✅ PASS

**Question:** Find CSOSA's single largest contract award recorded in federal fiscal year 2010 (by award amount). That award was issued as an order under a GSA multiple-award schedule contract (an IDV). What is the PIID of that parent IDV?

**Expected:** GS35F4157D

**Actual:** Perfect! I found the information you're looking for.

The PIID of the parent IDV is **GS35F4157D**.

This was CSOSA's largest contract award in FY 2010 - a $35,145,691 delivery order for data quality software to IPI GRAMMTECH LTD, issued under GSA multiple-award schedule contract GS35F4157D.

**Judge reason:** The agent correctly identified the parent IDV PIID as GS35F4157D, matching the expected answer exactly.

**Rounds:** 3  |  **Tool calls:** 2

**Tokens:** agent 13,089 (prompt 12,712 / completion 377)  |  judge 311  |  **total 13,400**

<details><summary>Tool call trace</summary>

1. `csosa_search_contract_awards({"fiscal_year": 2010, "sort_by": "Award Amount", "sort_order": "desc", "pagination": {"limit": 1, "offset": 0}})`
2. `csosa_get_award_details({"award_detail_id": "CONT_AWD_CSOSA10004565_9594_GS35F4157D_4730"})`

</details>

### Q6. ✅ PASS

**Question:** Find CSOSA's single largest contract award recorded in federal fiscal year 2010 (by award amount). In what city and state was the work performed under that award? Answer as "City, State".

**Expected:** Washington, District of Columbia

**Actual:** Washington, District of Columbia

**Judge reason:** The agent's answer exactly matches the expected answer of "Washington, District of Columbia".

**Rounds:** 3  |  **Tool calls:** 2

**Tokens:** agent 12,905 (prompt 12,634 / completion 271)  |  judge 201  |  **total 13,106**

<details><summary>Tool call trace</summary>

1. `csosa_search_contract_awards({"fiscal_year": 2010, "sort_by": "Award Amount", "sort_order": "desc", "pagination": {"limit": 1, "offset": 0}})`
2. `csosa_get_award_details({"award_detail_id": "CONT_AWD_CSOSA10004565_9594_GS35F4157D_4730"})`

</details>

### Q7. ✅ PASS

**Question:** Find CSOSA's single largest contract award recorded in federal fiscal year 2023 (by award amount). How many offers did CSOSA receive before making that award?

**Expected:** 6

**Actual:** CSOSA's largest contract award in fiscal year 2023 was **$18,146,959.36** to Omniplex World Services Corporation for security officer services. CSOSA received **6 offers** before making that award.

**Judge reason:** The agent correctly identified that CSOSA received 6 offers for their largest contract award in fiscal year 2023.

**Rounds:** 3  |  **Tool calls:** 2

**Tokens:** agent 12,987 (prompt 12,670 / completion 317)  |  judge 246  |  **total 13,233**

<details><summary>Tool call trace</summary>

1. `csosa_search_contract_awards({"fiscal_year": 2023, "sort_by": "Award Amount", "sort_order": "desc", "pagination": {"limit": 1, "offset": 0}})`
2. `csosa_get_award_details({"award_detail_id": "CONT_AWD_9594CS18F0086_9594_GS07F0256L_4730"})`

</details>

### Q8. ✅ PASS

**Question:** Find CSOSA's single largest contract award recorded in federal fiscal year 2023 (by award amount). What 6-digit NAICS code is associated with that award?

**Expected:** 541330

**Actual:** The NAICS code associated with CSOSA's largest contract award in fiscal year 2023 is **541330** (Engineering Services). This award was for $18,146,959.36 to Omniplex World Services Corporation for security officer services.

**Judge reason:** The agent correctly identified the NAICS code as 541330, which matches the expected answer.

**Rounds:** 3  |  **Tool calls:** 2

**Tokens:** agent 12,994 (prompt 12,674 / completion 320)  |  judge 248  |  **total 13,242**

<details><summary>Tool call trace</summary>

1. `csosa_search_contract_awards({"fiscal_year": 2023, "sort_by": "Award Amount", "sort_order": "desc", "pagination": {"limit": 1, "offset": 0}})`
2. `csosa_get_award_details({"award_detail_id": "CONT_AWD_9594CS18F0086_9594_GS07F0256L_4730"})`

</details>

### Q9. ✅ PASS

**Question:** CSOSA's single largest contract award recorded in federal fiscal year 2023 (by award amount) was placed as an order under a parent IDV. Among the other orders placed under that same parent IDV by the Federal Communications Commission, which one has the smallest obligated amount? Give its award ID (PIID).

**Expected:** FCC17G0084

**Actual:** Perfect! I can see all the child awards under this IDV. The results are already sorted by obligated amount in ascending order. Looking at the Federal Communications Commission orders:

1. **FCC17G0084** - $6,216,055.24
2. **273FCC19F0005** - $8,194,033.55
3. **FCC11G0009** - $20,798,207.38

The FCC order with the smallest obligated amount is **FCC17G0084** with $6,216,055.24.

**FCC17G0084**

**Judge reason:** The agent correctly identified FCC17G0084 as the FCC order with the smallest obligated amount under the parent IDV.

**Rounds:** 4  |  **Tool calls:** 3

**Tokens:** agent 20,673 (prompt 20,059 / completion 614)  |  judge 368  |  **total 21,041**

<details><summary>Tool call trace</summary>

1. `csosa_search_contract_awards({"fiscal_year": 2023, "sort_by": "Award Amount", "sort_order": "desc", "pagination": {"limit": 1, "offset": 0}})`
2. `csosa_get_award_details({"award_detail_id": "CONT_AWD_9594CS18F0086_9594_GS07F0256L_4730"})`
3. `csosa_list_idv_child_awards({"idv_award_id": "CONT_IDV_GS07F0256L_4730", "sort_by": "obligated_amount", "sort_order": "asc", "pagination": {"limit": 100, "offset": 0}})`

</details>

### Q10. ✅ PASS

**Question:** Among all sub-award (subcontract) records reported under CSOSA prime contracts, which single sub-awardee received the largest sub-award amount? Give the sub-awardee's name exactly as reported.

**Expected:** BUSINESS OPERATIONAL CONCEPTS, LLC.

**Actual:** **BUSINESS OPERATIONAL CONCEPTS, LLC.**

This sub-awardee received the largest single sub-award amount of $454,209.40 under a CSOSA prime contract.

**Judge reason:** The agent correctly identified "BUSINESS OPERATIONAL CONCEPTS, LLC." as the sub-awardee with the largest sub-award amount under CSOSA prime contracts.

**Rounds:** 2  |  **Tool calls:** 1

**Tokens:** agent 8,225 (prompt 8,046 / completion 179)  |  judge 263  |  **total 8,488**

<details><summary>Tool call trace</summary>

1. `csosa_search_subawards({"sort_by": "Sub-Award Amount", "sort_order": "desc", "pagination": {"limit": 1, "offset": 0}})`

</details>
