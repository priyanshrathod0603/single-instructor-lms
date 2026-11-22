# Universal Engineering Rulebook (GLOBAL_RULES)

## 1. Fundamental Scope & Authority

This document defines the universal, non-negotiable engineering rules governing every AI coding agent, automated workflow, and technical activity within the **Single-Instructor Learning Management System (LMS)** project.

These global rules supersede all local preferences, framework conventions, and arbitrary AI optimizations. They apply universally across every other rulebook in `.ai/RULES/`, every workflow in `.ai/WORKFLOWS/`, and every task executed in the repository.

---

## 2. Rule 1: Project Identity & Business Model Boundaries

* **The Business Formula**:
  $$\text{ONE INSTRUCTOR} \longrightarrow \text{ONE BRAND} \longrightarrow \text{MULTIPLE COURSES} \longrightarrow \text{MULTIPLE STUDENTS} \longrightarrow \text{DIRECT SALES}$$
* **Mandatory AI Behavior**:
  * Every feature, schema, and API contract must serve this single-instructor, single-brand educational model.
* **Prohibited Actions (Absolute Restrictions)**:
  * NEVER introduce multi-tenant school or university ERP hierarchies.
  * NEVER introduce multi-instructor open marketplace mechanisms (e.g., third-party instructor registration, vendor commissions, marketplace search across competing instructors).
  * NEVER introduce generic SaaS sub-organization logic without explicit owner instruction.

---

## 3. Rule 2: Project Owner Authority & AI Subordination

* **Principle**: The user is the **Project Owner**. The AI is a technical developer and implementation assistant. The AI possesses **zero** product ownership authority.
* **Mandatory AI Behavior**:
  * Respect the Project Owner's explicit directives as the highest authority in the priority hierarchy.
  * Defer all business decisions, aesthetic choices, and scope adjustments to the owner.
* **Prohibited Actions**:
  * NEVER interpret silence or absence of explicit prohibition as approval.
  * NEVER make assumptions about what the owner "probably wants" and execute them.
  * NEVER override an owner requirement based on general industry trends or AI training bias.

---

## 4. Rule 3: Zero Unauthorized Changes (Strict Scope Control)

* **Principle**: Approval for one specific task does **NOT** authorize changes to unrelated files, features, configurations, or architectures.
* **Mandatory Scope Control Protocol**:
  1. **Understand**: Deconstruct the user prompt into exact deliverables, constraints, and non-goals.
  2. **Inspect**: Identify the absolute minimum set of files and functions required to satisfy the request.
  3. **Bound**: Define the task boundary in `.ai/CONTEXT/ACTIVE_TASK.md` before editing any file.
  4. **Execute**: Modify strictly what is inside the defined scope.
* **Prohibited Actions (Absolute Restrictions)**:
  * NEVER independently add features not requested.
  * NEVER independently remove existing features.
  * NEVER independently modify existing functionality or business logic.
  * NEVER independently refactor working code.
  * NEVER rewrite existing modules to match "cleaner" personal aesthetics.
  * NEVER delete, rename, or move existing files without explicit authorization.

---

## 5. Rule 4: Stop-and-Ask Procedure for Out-of-Scope Work

* **Trigger**: If, during task execution, the AI discovers that completing the task requires modifying an external file, modifying an API contract, running a database migration, altering a shared component, or introducing a new dependency:
* **Protocol**:
  1. **STOP IMMEDIATELY**. Do not apply speculative edits.
  2. Formulate a structured escalation explaining:
     * **What additional change is required**.
     * **Why it is necessary** (root technical cause).
     * **Which files and functions are affected**.
     * **Potential risks, regressions, or side effects**.
  3. Present the escalation to the Project Owner and await explicit written approval before proceeding.

---

## 6. Rule 5: Zero Technology Stack Drift

* **Principle**: The technology stack is locked. Recommendations in the blueprint PDF are proposed defaults, not pre-approved migration authorizations.
* **Mandatory AI Behavior**:
  * Inspect package manifests and repository state to verify the installed reality before making technical claims.
* **Prohibited Actions**:
  * NEVER independently change programming languages, frontend/backend frameworks, or ORMs.
  * NEVER install, remove, upgrade, or downgrade dependencies without explicit approval.
  * NEVER modify environment files (`.env`), build pipelines, Docker files, or CI/CD configurations.

---

## 7. Rule 6: Zero Design Autonomy

* **Principle**: The project possesses an official, owner-approved visual design system: **Modern Playful Minimalist**.
* **Mandatory AI Behavior**:
  * Adhere strictly to the approved design tokens, color palette, typography scale, and layout ratios defined in `.ai/RULES/UI_UX_RULES.md`.
* **Prohibited Actions**:
  * NEVER introduce arbitrary colors, random hex codes, or unapproved fonts.
  * NEVER redesign existing components, cards, buttons, or dashboard layouts.
  * NEVER adopt generic dark-heavy SaaS or excessive glassmorphic aesthetics.

---

## 8. Rule 7: Preservation of Existing Working Functionality

* **Principle**: Working code is sacred. A new feature must never compromise existing features.
* **Mandatory AI Behavior**:
  * Inspect existing tests, callers, and dependencies before modifying any function.
  * Formulate regression checks covering adjacent modules.
* **Prohibited Actions**:
  * NEVER simplify or delete existing logic to make an implementation easier.
  * NEVER comment out failing assertions or disable security guards to make tests pass.

---

## 9. Rule 8: Mandatory Context & Tracking Synchronization

* **Principle**: Every engineering session and completed task must be permanently recorded to prevent AI knowledge decay across restarts.
* **Mandatory AI Behavior**:
  * After completing any task, update all 4 context files:
    1. `.ai/CONTEXT/CURRENT_STATE.md`
    2. `.ai/CONTEXT/ACTIVE_TASK.md`
    3. `.ai/CONTEXT/NEXT_ACTION.md`
    4. `.ai/CONTEXT/RECOVERY_SNAPSHOT.md`
  * Update all 4 tracking files:
    1. `.ai/TRACKING/CHANGELOG.md`
    2. `.ai/TRACKING/TASK_HISTORY.md`
    3. `.ai/TRACKING/ERROR_LOG.md`
    4. `.ai/TRACKING/AUDIT_LOG.md`
* **Prohibited Actions**:
  * NEVER skip context updates to "save time".
  * NEVER fabricate completion records or claim features are implemented without empirical verification.

---

## 10. Rule 9: Evidence-Based Reporting Standard

* **Principle**: All technical claims must be grounded in physical codebase evidence.
* **Mandatory Reporting Format**:
  Every task completion report must state:
  1. Exact files inspected and modified.
  2. Commands executed and their terminal outputs.
  3. Tests run, with pass/fail counts.
  4. Confirmation that no unauthorized changes were made.
  5. Remaining limitations or unverified areas.
