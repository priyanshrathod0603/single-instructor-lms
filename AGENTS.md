# AI Engineering Agent Guidelines & Operating Directives

Welcome to the **Single-Instructor Learning Management System (LMS)** project.

---

## 1. Project Context & Operating Model

This product is a proprietary direct-to-student educational platform built for an expert instructor:
$$\text{ONE INSTRUCTOR} \longrightarrow \text{ONE BRAND} \longrightarrow \text{MULTIPLE COURSES} \longrightarrow \text{MULTIPLE STUDENTS} \longrightarrow \text{DIRECT SALES}$$

* **Specification Source**: `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` [Source: LMS Blueprint v2.0, Pages 1–16].
* **Explicit Boundary**: This is **NOT** a multi-institute ERP, and it is **NOT** an open marketplace like Udemy or Coursera.

---

## 2. Mandatory Entry Protocol (Read Before Doing Any Work)

Before writing code, editing files, running migrations, or planning tasks, you **MUST** read the following documents in order:
1. [.ai/CORE/IDENTITY.md](file:///Users/priyansh/lms/.ai/CORE/IDENTITY.md) — Product model, agent charter, and non-goals.
2. [.ai/CORE/PRIORITY_HIERARCHY.md](file:///Users/priyansh/lms/.ai/CORE/PRIORITY_HIERARCHY.md) — 8-tier authority hierarchy for resolving conflicts.
3. [.ai/CONTEXT/CURRENT_STATE.md](file:///Users/priyansh/lms/.ai/CONTEXT/CURRENT_STATE.md) — Latest verified status, active phase, and blockers.
4. [.ai/CONTEXT/ACTIVE_TASK.md](file:///Users/priyansh/lms/.ai/CONTEXT/ACTIVE_TASK.md) — Active task scope and execution plan.
5. [.ai/WORKFLOWS/SESSION_RECOVERY.md](file:///Users/priyansh/lms/.ai/WORKFLOWS/SESSION_RECOVERY.md) — 15-step recovery sequence for context rehydration.

---

## 3. Strict Operating Invariants & Guardrails

1. **Reserved Files Policy**: The following 17 files are strictly reserved for the project owner:
   * `.ai/CORE/GOLDEN_RULES.md`
   * `.ai/RULES/*` (10 files)
   * `.ai/GOVERNANCE/*` (5 files)
   * `.ai/USER_WORKFLOW.md`
   * **Rule**: Do **NOT** populate, invent policies for, or modify these files.
2. **Single-Active-Session Invariant**: At most one active session per user account in `auth_sessions`. A newly authenticated login atomically revokes the prior session [Source: LMS Blueprint v2.0, Page 8].
3. **Course Revision Immutability**: Published course revisions are immutable; edits create a new draft revision [Source: LMS Blueprint v2.0, Page 5].
4. **Zero Trust on Browser Redirect**: Course enrollment is granted **only** via verified payment webhook; never on client browser redirect [Source: LMS Blueprint v2.0, Page 14].
5. **Preserve Working Code**: Never refactor, simplify, or delete working features without an approved plan and verified regression tests.
6. **No Fabricated Claims**: Never state that a feature is implemented or tests pass without empirical evidence in the session.

For the full intelligence system map, see [.ai/README.md](file:///Users/priyansh/lms/.ai/README.md).
