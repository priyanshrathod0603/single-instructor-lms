# Defect & Bug History Register

This document tracks all confirmed defects, regressions, security vulnerabilities, and logic flaws encountered throughout the lifecycle of the Single-Instructor LMS.

> **Operational Principle**:
> Never invent bugs. Never fabricate fictional bug histories. Active and historical defects must reflect real, observed anomalies during development, testing, or production operations.

---

## 1. Defect Classification Standard

| Severity Level | Definition | Target Resolution SLA |
| :--- | :--- | :--- |
| `BLOCKER` / `CRITICAL` | Security breach, data loss, session bypass, payment corruption, broken build. | Immediate halt of other work |
| `HIGH` | Core workflow broken (e.g., student unable to submit assignment or take quiz). | 24 Hours |
| `MEDIUM` | Non-critical workflow failure, UI rendering glitch, or validation bug with workaround. | Current Sprint |
| `LOW` | Minor visual defect, cosmetic typo, or non-blocking edge case. | Backlog Priority |

---

## 2. Active Unresolved Defects

*No active defects currently recorded. The project is currently in Phase 0 (Initialization).*

---

## 3. Historical Resolved Defects

*No historical defects currently recorded. Register initialized on 2026-11-13.*

---

## 4. Defect Logging Template (Mandatory Format for Future Agents)

When an agent or engineer identifies a bug, they must append an entry using the following standard template:

```markdown
### BUG-[ID]: [Descriptive Title]
* **Module**: [e.g., MOD-02 Auth, MOD-08 Commerce]
* **Severity**: [CRITICAL | HIGH | MEDIUM | LOW]
* **Priority**: [P0 | P1 | P2 | P3]
* **Status**: [OPEN | IN_INVESTIGATION | RESOLVED | CANNOT_REPRODUCE]
* **Date Reported**: YYYY-MM-DD
* **Discovered By**: [Agent / Test Suite / User]
* **Affected Files**:
  * `path/to/affected/file.ext`
* **Reproduction Steps**:
  1. Navigate to ...
  2. Send request payload ...
  3. Observe error ...
* **Expected Result**: [What should have occurred according to specification]
* **Actual Result**: [What actually occurred, including HTTP status / stack trace]
* **Root Cause Analysis**: [Technical explanation of the underlying fault]
* **Remediation Implemented**: [Summary of the exact code fix applied]
* **Verification Evidence**: [Output of test run proving fix works]
* **Regression Prevention**: [Unit/Integration test added to prevent recurrence]
* **Related Tasks**: [TASK-ID]
```
