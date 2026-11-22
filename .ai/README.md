# Project Intelligence, Memory & Governance System

Welcome to the AI Intelligence System for the **Single-Instructor Learning Management System (LMS)**.

This repository directory (`.ai/`) serves as the permanent, authoritative source of project knowledge, architecture specifications, engineering workflows, operational tracking, and governance rules for AI coding assistants and human engineers alike.

---

## 1. Directory Structure & Map

```text
.ai/
├── README.md                      # Master Index & Intelligence Architecture Map
├── USER_WORKFLOW.md               # [RESERVED] User-Specific Interaction Workflows
│
├── CORE/                          # Core Identity & Fundamental Operating Directives
│   ├── IDENTITY.md                # Agent Identity, Product Model & Responsibilities
│   ├── BEHAVIOUR.md               # 4-Phase Operating Protocols & Edge Case Rules
│   ├── PRIORITY_HIERARCHY.md      # 8-Tier Conflict Resolution Hierarchy
│   └── GOLDEN_RULES.md            # [RESERVED] Core Immutable Golden Rules
│
├── RULES/                         # [RESERVED] Engineering Domain Policies (Pending Owner Input)
│   ├── GLOBAL_RULES.md            # [RESERVED] Global System Standards
│   ├── FRONTEND_RULES.md          # [RESERVED] Client Framework & State Rules
│   ├── BACKEND_RULES.md           # [RESERVED] API & Service Architecture Rules
│   ├── API_RULES.md               # [RESERVED] REST Endpoint & Payload Rules
│   ├── DATABASE_RULES.md          # [RESERVED] PostgreSQL Schema & Migration Rules
│   ├── SECURITY_RULES.md          # [RESERVED] Auth, Session & Sanitization Rules
│   ├── CONFIGURATION_RULES.md     # [RESERVED] Environment & Secret Management
│   ├── UI_UX_RULES.md             # [RESERVED] Design System & Accessibility Rules
│   ├── TESTING_RULES.md           # [RESERVED] Test Suite Coverage & Verification Rules
│   └── GIT_RULES.md               # [RESERVED] Branching & Commit Conventions
│
├── GOVERNANCE/                    # [RESERVED] Change Control & Authority Guardrails
│   ├── CHANGE_CONTROL.md          # [RESERVED] Architectural Mutation Governance
│   ├── PERMISSION_MATRIX.md       # [RESERVED] Formal Role Permission Authority
│   ├── PROTECTED_FILES.md         # [RESERVED] Restricted File Modification Policies
│   ├── DESTRUCTIVE_ACTIONS.md     # [RESERVED] Database & Asset Purge Safeguards
│   └── APPROVAL_WORKFLOW.md       # [RESERVED] Stakeholder Sign-Off Workflows
│
├── MEMORY/                        # Persistent Project Knowledge & Requirements Truth
│   ├── PROJECT_MEMORY.md          # High-Level Product Overview & Invariants
│   ├── USER_REQUIREMENTS.md       # 25+ Granular Requirements Across 10 Modules
│   ├── ARCHITECTURE.md            # System Architecture, Schemas & Transaction Bounds
│   ├── TECH_STACK.md              # Verified vs Proposed Stack & Pending Choices
│   ├── DECISIONS.md               # Permanent Architecture & Product Decision Register
│   ├── COMPLETED_TASKS.md         # Verified Completed Implementation Milestones
│   ├── PENDING_TASKS.md           # Implementation Phase Backlog (Phases 0–6)
│   ├── BUG_HISTORY.md             # Defect History, Root Causes & Regressions
│   └── SESSION_LOG.md             # Chronological AI Engineering Trajectory Journal
│
├── WORKFLOWS/                     # Standard Operating Procedures (SOPs)
│   ├── PROJECT_ANALYSIS.md        # Codebase & Architecture Investigation Protocol
│   ├── TASK_PLANNING.md           # 6-Step Task Planning & Impact Analysis Discipline
│   ├── IMPLEMENTATION.md          # 18-Step Implementation Lifecycle Standards
│   ├── DEBUGGING.md               # 10-Step Scientific Debugging Methodology
│   ├── TESTING.md                 # Test Matrix & QA Acceptance Protocol
│   ├── CODE_REVIEW.md             # 16-Point Quality, Security & Type Audit
│   └── SESSION_RECOVERY.md        # 15-Step Context Rehydration & Recovery Sequence
│
├── TRACKING/                      # Historical Audit & Lifecycle Telemetry
│   ├── CHANGELOG.md               # Versioned Chronological Project Changes
│   ├── TASK_HISTORY.md            # State Transitions & Task Audit Trail
│   ├── ERROR_LOG.md               # Sanitized Operational & Runtime Exceptions
│   └── AUDIT_LOG.md               # AI Engineering Actions Audit Log
│
└── CONTEXT/                       # Immediate Operational State & Handoff Controllers
    ├── CURRENT_STATE.md           # Verified Project Status & Module Readiness
    ├── ACTIVE_TASK.md             # In-Flight Task, Scope & Step-by-Step Plan
    ├── NEXT_ACTION.md             # Immediate Next Single Engineering Action
    └── RECOVERY_SNAPSHOT.md       # High-Density Session Continuation Snapshot
```

---

## 2. Classification of Documentation Files

To ensure clarity regarding authority and mutability, files are grouped into four operational categories:

| Category | Directories & Files | Authority & Mutability Guidelines |
| :--- | :--- | :--- |
| **Reserved Files** | `.ai/CORE/GOLDEN_RULES.md`<br>`.ai/RULES/*`<br>`.ai/GOVERNANCE/*`<br>`.ai/USER_WORKFLOW.md` | **Strictly Reserved**: These 17 files contain minimal initialization markers. AI agents must **NEVER** invent, generate, or populate policies in these files. Content is supplied exclusively by the project owner. |
| **Authoritative Baseline** | `.ai/CORE/IDENTITY.md`<br>`.ai/CORE/PRIORITY_HIERARCHY.md`<br>`.ai/MEMORY/USER_REQUIREMENTS.md`<br>`.ai/MEMORY/ARCHITECTURE.md`<br>`.ai/MEMORY/DECISIONS.md` | **Binding Specification**: Defines what the product must do, system invariants, database schemas, and approved technical choices. Changes require explicit user authorization. |
| **Operational Workflows** | `.ai/WORKFLOWS/*`<br>`.ai/CORE/BEHAVIOUR.md` | **Procedural Standards**: Guides how an AI agent investigates, plans, writes code, debugs, tests, and reviews pull requests. |
| **Living State & History** | `.ai/CONTEXT/*`<br>`.ai/TRACKING/*`<br>`.ai/MEMORY/SESSION_LOG.md`<br>`.ai/MEMORY/COMPLETED_TASKS.md` | **Dynamic Synchronization**: Updated dynamically at the start, midpoint, and completion of every development session to preserve continuity. |

---

## 3. Recommended Reading Orders

### A. New Agent Onboarding Reading Order (First Time Joining Project)
When an agent or developer first joins the project, read in this exact sequence:
1. [.ai/CORE/IDENTITY.md](file:///Users/priyansh/lms/.ai/CORE/IDENTITY.md) — Product model (`ONE INSTRUCTOR -> ONE BRAND -> DIRECT SALES`).
2. [.ai/CORE/PRIORITY_HIERARCHY.md](file:///Users/priyansh/lms/.ai/CORE/PRIORITY_HIERARCHY.md) — 8-tier hierarchy of authority and conflict rules.
3. [.ai/MEMORY/PROJECT_MEMORY.md](file:///Users/priyansh/lms/.ai/MEMORY/PROJECT_MEMORY.md) — High-level domain topology and invariants.
4. [.ai/MEMORY/USER_REQUIREMENTS.md](file:///Users/priyansh/lms/.ai/MEMORY/USER_REQUIREMENTS.md) — Complete requirements by module.
5. [.ai/MEMORY/ARCHITECTURE.md](file:///Users/priyansh/lms/.ai/MEMORY/ARCHITECTURE.md) — Relational schema, single-session invariant, transaction boundaries.
6. [.ai/MEMORY/TECH_STACK.md](file:///Users/priyansh/lms/.ai/MEMORY/TECH_STACK.md) — Verified repo facts vs proposed blueprint stack.
7. [.ai/MEMORY/DECISIONS.md](file:///Users/priyansh/lms/.ai/MEMORY/DECISIONS.md) — Approved baseline decisions vs pending choices.
8. [.ai/CONTEXT/CURRENT_STATE.md](file:///Users/priyansh/lms/.ai/CONTEXT/CURRENT_STATE.md) — Current development phase and status.

### B. Daily Session Recovery Sequence (Resuming In-Flight Work)
When resuming work after conversation reset or context interruption, execute the 15-step sequence in [.ai/WORKFLOWS/SESSION_RECOVERY.md](file:///Users/priyansh/lms/.ai/WORKFLOWS/SESSION_RECOVERY.md).

---

## 4. Documentation Maintenance Expectations

1. **Keep Context Synchronized**: Every task completion must update `.ai/MEMORY/COMPLETED_TASKS.md`, `.ai/TRACKING/CHANGELOG.md`, and `.ai/CONTEXT/CURRENT_STATE.md`.
2. **Never Fabricate Reality**: Never claim a feature is completed, tested, or installed without empirical evidence from the repository.
3. **Respect Reserved Files**: Do not write policy content into reserved `.ai/RULES/`, `.ai/GOVERNANCE/`, or `.ai/USER_WORKFLOW.md` files.
