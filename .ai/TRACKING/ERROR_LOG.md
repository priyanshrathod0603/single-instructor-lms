# Operational & Execution Error Log

This document records all systemic errors, environmental crashes, build failures, third-party provider timeouts, and infrastructure anomalies encountered during development and operations.

> **Privacy & Security Mandate**:
> Never log passwords, API secret keys, bearer tokens, session hashes, credit card details, or sensitive personal data in this file. All logged tokens must be redacted or replaced with cryptographic hashes.

---

## 1. Error Categories

* `BUILD_ERROR`: Compiler, bundler, type-checker, or packaging failures.
* `ENV_ERROR`: Missing environment variables, incorrect system PATH, or binary incompatibilities.
* `DB_ERROR`: Connection pool exhaustion, deadlocks, migration errors, or constraint violations.
* `PROVIDER_ERROR`: External API outages, rate limits, or network failures (Razorpay, transcode provider, email mailer).
* `RUNTIME_ERROR`: Unhandled 500 exceptions, race condition crashes, or panic states.

---

## 2. Chronological Error Records

* **Task TASK-GOV-001 (2026-11-13)**: No errors or warnings were observed during the task. All 10 engineering rulebooks in `.ai/RULES/` were written and validated cleanly without filesystem, syntax, or execution exceptions.
* **Task TASK-INIT-001 (2026-11-13)**: Initialized clean error log; no operational or runtime errors observed.

---

## 3. Error Logging Template (Mandatory Standard)

```markdown
### ERR-[ID]: [Brief Summary]
* **Timestamp**: YYYY-MM-DDTHH:MM:SSZ
* **Category**: [BUILD_ERROR | ENV_ERROR | DB_ERROR | PROVIDER_ERROR | RUNTIME_ERROR]
* **Module**: [e.g., MOD-02 Auth, MOD-08 Commerce]
* **Environment**: [Local / Staging / Production]
* **Status**: [OPEN | INVESTIGATING | RESOLVED | MITIGATED]
* **Error Message**:
  ```text
  [Sanitized exception message / stack trace]
  ```
* **Context & Trigger**: [What request or background job triggered the error]
* **Root Cause**: [Underlying fault]
* **Remediation / Resolution**: [Steps taken to fix or mitigate]
* **Related Bug / Task**: [BUG-ID / TASK-ID]
```
