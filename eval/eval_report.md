# CSOSA MCP Server — Gold Question Evaluation Report

Model: `databricks-claude-sonnet-4-5`  |  Questions: 14  |  Accuracy: 14/14 (100%)
Average tool calls per question: 1.6  |  Average rounds per question: 2.6  |  Average tokens per question: 12,083

## Interpretation

**Final result: 14/14 (100%).** Questions 1–10 are the original gold set (see
history below); questions 11–14 were added specifically to address Finding 3
below — weak coverage of the two newer tools.

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

- **Finding 3 — resolved.** The original 10-question set exercised
  `csosa_search_subawards` and `csosa_list_idv_child_awards` exactly once
  each, giving weak signal on those two tools specifically. Q11–Q14 target
  them deliberately (a rank-3 sub-award lookup, a keyword+location sub-award
  query, and a second, different parent IDV with its own child-award chain —
  verified against live data the same way as the original set, following the
  same "query first, write the gold answer from what's actually there"
  process documented in Finding 1). Result: `csosa_search_subawards` now has
  3 calls and `csosa_list_idv_child_awards` has 2, both across a genuinely
  different IDV/sub-award than the original set used — real additional
  coverage, not a duplicate of the same lucky path.

- No question needed anywhere close to `MAX_TOOL_ROUNDS` (8) or many pages of
  results — average 1.6 tool calls and 2.6 rounds per question. The agent
  resolved every multi-hop chain in the minimum number of calls (search →
  details → [IDV children]), with no backtracking or redundant calls observed
  in any trace.

- **Token usage:** ~165k agent tokens to answer all 14 questions
  (~12.1k average, mostly prompt tokens from the tool-calling loop's system
  prompt plus accumulating tool results) and ~4k to the LLM judge grading
  them — judging costs roughly 2.4% of what answering does, consistent with
  the earlier 10-question run.

## Token usage across all questions

Counts come from the `usage` field each serving-endpoint response returns; 0 for any endpoint that doesn't report it. "Agent" is answering the question (all tool-calling rounds); "Judge" is the separate LLM-as-judge grading call.

| | Prompt tokens | Completion tokens | Total |
|---|---|---|---|
| Agent | 160,763 | 4,387 | 165,150 |
| Judge | 3,458 | 549 | 4,007 |
| **Total** | **164,221** | **4,936** | **169,157** |

## Tool usage across all questions

| Tool | Calls |
|---|---|
| `csosa_search_contract_awards` | 7 |
| `csosa_get_award_details` | 7 |
| `csosa_spending_summary` | 4 |
| `csosa_search_subawards` | 3 |
| `csosa_list_idv_child_awards` | 2 |

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

This recipient received the highest total obligated amount ($35,145,691) from CSOSA prime contracts during federal fiscal years 2008-2020.

**Judge reason:** The agent correctly identified "IPI GRAMMTECH LTD" as the recipient with the highest total obligated amount from CSOSA prime contracts during the specified period.

**Rounds:** 2  |  **Tool calls:** 1

**Tokens:** agent 8,046 (prompt 7,844 / completion 202)  |  judge 273  |  **total 8,319**

<details><summary>Tool call trace</summary>

1. `csosa_spending_summary({"group_by": "recipient", "start_date": "2007-10-01", "end_date": "2020-09-30", "limit": 1})`

</details>

### Q4. ✅ PASS

**Question:** Considering only federal fiscal years 2008 through 2020 (inclusive), which Product or Service Code category received the highest total CSOSA contract obligations?

**Expected:** SOCIAL- SOCIAL REHABILITATION

**Actual:** **SOCIAL- SOCIAL REHABILITATION** received the highest total CSOSA contract obligations during federal fiscal years 2008-2020, with **$68,103,288.60** in obligations.

**Judge reason:** The agent correctly identified "SOCIAL- SOCIAL REHABILITATION" as the Product or Service Code category with the highest total CSOSA contract obligations for fiscal years 2008-2020.

**Rounds:** 2  |  **Tool calls:** 1

**Tokens:** agent 8,197 (prompt 7,995 / completion 202)  |  judge 254  |  **total 8,451**

<details><summary>Tool call trace</summary>

1. `csosa_spending_summary({"group_by": "product_or_service", "start_date": "2007-10-01", "end_date": "2020-09-30", "limit": 10})`

</details>

### Q5. ✅ PASS

**Question:** Find CSOSA's single largest contract award recorded in federal fiscal year 2010 (by award amount). That award was issued as an order under a GSA multiple-award schedule contract (an IDV). What is the PIID of that parent IDV?

**Expected:** GS35F4157D

**Actual:** Perfect! I found the information you need.

**GS35F4157D**

This is the PIID of the parent GSA multiple-award schedule contract (IDV) under which CSOSA's largest FY 2010 contract award was issued. That award was for $35,145,691 to IPI GRAMMTECH LTD for data quality software.

**Judge reason:** The agent correctly identified the PIID as GS35F4157D, matching the expected answer exactly.

**Rounds:** 3  |  **Tool calls:** 2

**Tokens:** agent 13,082 (prompt 12,712 / completion 370)  |  judge 301  |  **total 13,383**

<details><summary>Tool call trace</summary>

1. `csosa_search_contract_awards({"fiscal_year": 2010, "sort_by": "Award Amount", "sort_order": "desc", "pagination": {"limit": 1, "offset": 0}})`
2. `csosa_get_award_details({"award_detail_id": "CONT_AWD_CSOSA10004565_9594_GS35F4157D_4730"})`

</details>

### Q6. ✅ PASS

**Question:** Find CSOSA's single largest contract award recorded in federal fiscal year 2010 (by award amount). In what city and state was the work performed under that award? Answer as "City, State".

**Expected:** Washington, District of Columbia

**Actual:** Washington, District of Columbia

**Judge reason:** The agent's answer exactly matches the expected answer for the city and state where the work was performed.

**Rounds:** 3  |  **Tool calls:** 2

**Tokens:** agent 12,905 (prompt 12,634 / completion 271)  |  judge 204  |  **total 13,109**

<details><summary>Tool call trace</summary>

1. `csosa_search_contract_awards({"fiscal_year": 2010, "sort_by": "Award Amount", "sort_order": "desc", "pagination": {"limit": 1, "offset": 0}})`
2. `csosa_get_award_details({"award_detail_id": "CONT_AWD_CSOSA10004565_9594_GS35F4157D_4730"})`

</details>

### Q7. ✅ PASS

**Question:** Find CSOSA's single largest contract award recorded in federal fiscal year 2023 (by award amount). How many offers did CSOSA receive before making that award?

**Expected:** 6

**Actual:** CSOSA's largest contract award in fiscal year 2023 was **$18,146,959.36** to Omniplex World Services Corporation for security officer services. 

CSOSA received **6 offers** before making that award.

**Judge reason:** The agent correctly identified that CSOSA received 6 offers for their largest FY2023 contract award.

**Rounds:** 3  |  **Tool calls:** 2

**Tokens:** agent 12,991 (prompt 12,671 / completion 320)  |  judge 247  |  **total 13,238**

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

**Tokens:** agent 12,990 (prompt 12,672 / completion 318)  |  judge 248  |  **total 13,238**

<details><summary>Tool call trace</summary>

1. `csosa_search_contract_awards({"fiscal_year": 2023, "sort_by": "Award Amount", "sort_order": "desc", "pagination": {"limit": 1, "offset": 0}})`
2. `csosa_get_award_details({"award_detail_id": "CONT_AWD_9594CS18F0086_9594_GS07F0256L_4730"})`

</details>

### Q9. ✅ PASS

**Question:** CSOSA's single largest contract award recorded in federal fiscal year 2023 (by award amount) was placed as an order under a parent IDV. Among the other orders placed under that same parent IDV by the Federal Communications Commission, which one has the smallest obligated amount? Give its award ID (PIID).

**Expected:** FCC17G0084

**Actual:** Perfect! I can see all the child awards under this IDV. Looking at the results sorted by obligated amount (ascending), I can identify the FCC orders:

1. **FCC17G0084** - $6,216,055.24 (Federal Communications Commission) - **SMALLEST FCC ORDER**
2. **273FCC19F0005** - $8,194,033.55 (Federal Communications Commission)
3. **FCC11G0009** - $20,798,207.38 (Federal Communications Commission)

The FCC order with the smallest obligated amount is **FCC17G0084** with $6,216,055.24.

**FCC17G0084**

**Judge reason:** The agent correctly identified FCC17G0084 as the FCC order with the smallest obligated amount under the parent IDV.

**Rounds:** 4  |  **Tool calls:** 3

**Tokens:** agent 20,710 (prompt 20,066 / completion 644)  |  judge 393  |  **total 21,103**

<details><summary>Tool call trace</summary>

1. `csosa_search_contract_awards({"fiscal_year": 2023, "sort_by": "Award Amount", "sort_order": "desc", "pagination": {"limit": 1, "offset": 0}})`
2. `csosa_get_award_details({"award_detail_id": "CONT_AWD_9594CS18F0086_9594_GS07F0256L_4730"})`
3. `csosa_list_idv_child_awards({"idv_award_id": "CONT_IDV_GS07F0256L_4730", "sort_by": "obligated_amount", "sort_order": "asc", "pagination": {"limit": 100, "offset": 0}})`

</details>

### Q10. ✅ PASS

**Question:** Among all sub-award (subcontract) records reported under CSOSA prime contracts, which single sub-awardee received the largest sub-award amount? Give the sub-awardee's name exactly as reported.

**Expected:** BUSINESS OPERATIONAL CONCEPTS, LLC.

**Actual:** **BUSINESS OPERATIONAL CONCEPTS, LLC.**

**Judge reason:** The agent's answer matches the expected sub-awardee name exactly, with only minor formatting differences (bold styling) that don't affect the factual content.

**Rounds:** 2  |  **Tool calls:** 1

**Tokens:** agent 8,202 (prompt 8,050 / completion 152)  |  judge 230  |  **total 8,432**

<details><summary>Tool call trace</summary>

1. `csosa_search_subawards({"sort_by": "Sub-Award Amount", "sort_order": "desc", "pagination": {"limit": 1, "offset": 0}})`

</details>

### Q11. ✅ PASS

**Question:** Among all CSOSA sub-award records, which single sub-awardee received the third-largest sub-award amount? Give the sub-awardee's name exactly as reported.

**Expected:** ARCHIMA LLC

**Actual:** Based on the search results, I can see the top sub-awards sorted by amount in descending order. The third-largest sub-award amount is $200,720.00, and the sub-awardee is:

**ARCHIMA LLC**

**Judge reason:** The agent correctly identified ARCHIMA LLC as the sub-awardee with the third-largest sub-award amount.

**Rounds:** 2  |  **Tool calls:** 1

**Tokens:** agent 10,473 (prompt 10,276 / completion 197)  |  judge 254  |  **total 10,727**

<details><summary>Tool call trace</summary>

1. `csosa_search_subawards({"sort_by": "Sub-Award Amount", "sort_order": "desc", "pagination": {"limit": 100, "offset": 0}})`

</details>

### Q12. ✅ PASS

**Question:** Among CSOSA sub-award records, which prime recipient issued sub-awards for "Salesforce support" work to a sub-awardee located in North Bethesda, Maryland? Give the prime recipient's name exactly as reported.

**Expected:** ACUMEN SOLUTIONS, INC.

**Actual:** Perfect! I found the records. Looking at the sub-awards for "Salesforce support" work, I can see that sub-awards were issued to DELANEY ADVANTAGE TECHNOLOGIES L.L.C. located in North Bethesda, Maryland (city_name: "NORTH BETHESDA", state_code: "MD").

The prime recipient that issued these sub-awards is:

**ACUMEN SOLUTIONS, INC.**

**Judge reason:** The agent correctly identified the prime recipient as "ACUMEN SOLUTIONS, INC." which matches the expected answer exactly.

**Rounds:** 2  |  **Tool calls:** 1

**Tokens:** agent 9,138 (prompt 8,903 / completion 235)  |  judge 314  |  **total 9,452**

<details><summary>Tool call trace</summary>

1. `csosa_search_subawards({"query": "Salesforce support", "pagination": {"limit": 100, "offset": 0}})`

</details>

### Q13. ✅ PASS

**Question:** CSOSA's delivery order to Bradley Technologies Inc for security services (signed 2023-09-08) was placed under a parent IDV. Among the Department of Defense's orders placed under that same parent IDV, which one has the largest obligated amount? Give its award ID (PIID).

**Expected:** FA480022F0003

**Actual:** Perfect! I can see all the child awards under this parent IDV. Among the Department of Defense orders, there are two:

1. **FA480022F0003** - Facility Access Control - $2,980,511.84 (Department of Defense)
2. **HC104726F0031** - DISA/DCDC Operations Command Security Desk Support - $169,135.20 (Department of Defense)

The Department of Defense order with the largest obligated amount is **FA480022F0003** with $2,980,511.84.

**Judge reason:** The agent correctly identified FA480022F0003 as the DoD order with the largest obligated amount under the parent IDV.

**Rounds:** 4  |  **Tool calls:** 3

**Tokens:** agent 18,925 (prompt 18,328 / completion 597)  |  judge 355  |  **total 19,280**

<details><summary>Tool call trace</summary>

1. `csosa_search_contract_awards({"recipient_name": "Bradley Technologies Inc", "query": "security services", "start_date": "2023-09-01", "end_date": "2023-09-15"})`
2. `csosa_get_award_details({"award_detail_id": "CONT_AWD_9594CS23F0072_9594_47QSWA20D0035_4732"})`
3. `csosa_list_idv_child_awards({"idv_award_id": "CONT_IDV_47QSWA20D0035_4732", "sort_by": "obligated_amount", "sort_order": "desc", "pagination": {"limit": 100, "offset": 0}})`

</details>

### Q14. ✅ PASS

**Question:** CSOSA's delivery order to Bradley Technologies Inc for security services (signed 2023-09-08) — what Product/Service Code (PSC) is associated with that award? Give the PSC code.

**Expected:** R430

**Actual:** **R430**

**Judge reason:** The agent's answer of R430 matches the expected PSC code exactly.

**Rounds:** 3  |  **Tool calls:** 2

**Tokens:** agent 12,938 (prompt 12,669 / completion 269)  |  judge 198  |  **total 13,136**

<details><summary>Tool call trace</summary>

1. `csosa_search_contract_awards({"recipient_name": "Bradley Technologies Inc", "query": "security services", "start_date": "2023-09-08", "end_date": "2023-09-08"})`
2. `csosa_get_award_details({"award_detail_id": "CONT_AWD_9594CS23F0072_9594_47QSWA20D0035_4732"})`

</details>
