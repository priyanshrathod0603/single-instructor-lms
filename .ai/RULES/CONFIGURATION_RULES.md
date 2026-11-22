# Configuration Management, Dependencies & Environment Lock (CONFIGURATION_RULES)

## 1. Technology Stack Lock & Configuration Scope

This document establishes strict change control over all application frameworks, runtime engines, package manifests, external cloud providers, environment variables, build pipelines, and deployment scripts for the Single-Instructor LMS.

All configuration activities must strictly adhere to the universal directives in [.ai/RULES/GLOBAL_RULES.md](file:///Users/priyansh/lms/.ai/RULES/GLOBAL_RULES.md) and stack classifications in [.ai/MEMORY/TECH_STACK.md](file:///Users/priyansh/lms/.ai/MEMORY/TECH_STACK.md).

---

## 2. Absolute Prohibitions (Zero Unauthorized Stack Changes)

The AI agent is **STRICTLY PROHIBITED** from independently executing any of the following actions without explicit, written Project Owner approval:
* **NEVER** switch, replace, or migrate the primary programming languages or frameworks.
* **NEVER** install new packages, libraries, or SDKs (`npm install`, `pip install`, `poetry add`, etc.).
* **NEVER** remove existing packages or dependencies.
* **NEVER** upgrade or downgrade dependency versions (`npm update`, `pip install --upgrade`).
* **NEVER** switch package management tools (e.g., swapping `npm` for `yarn`, `pnpm`, or `bun`; swapping `pip` for `poetry`).
* **NEVER** modify build configuration files (`tsconfig.json`, `next.config.js`, `vite.config.ts`, `pyproject.toml`, `webpack.config.js`).
* **NEVER** alter Docker configurations (`Dockerfile`, `docker-compose.yml`) or container runtimes.
* **NEVER** modify CI/CD pipeline definitions (`.github/workflows/*.yml`).
* **NEVER** change third-party hosting, database, media, or payment service providers.

---

## 3. Policy on Blueprint Recommendations vs. Approved Reality

* **The Reality Rule**: Recommendations, diagrams, or default stacks outlined in `Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf` are **proposals**, not pre-approved implementations.
* **Verification Mandate**: Before citing or relying upon any library, tool, or provider, the agent **MUST** inspect the actual repository filesystem to confirm whether it exists.
* **Migration Boundary**: If an AI agent believes a different library or framework would be superior, the agent **MUST STOP**, document the proposal in `.ai/MEMORY/DECISIONS.md` under `PENDING_APPROVAL`, and await owner sign-off.

---

## 4. Environment Variables & Secret Management Protocol

### 1. Protection of Existing Secrets
* **NEVER** overwrite an existing `.env` file with dummy or default values.
* **NEVER** delete or purge environment variables currently present in the environment.
* If a new environment variable is required by an approved feature:
  1. Add the variable with a descriptive placeholder to `.env.example`.
  2. Document the variable's purpose, default value, and security implications in [.ai/MEMORY/TECH_STACK.md](file:///Users/priyansh/lms/.ai/MEMORY/TECH_STACK.md).
  3. Inform the Project Owner that the variable must be provisioned in their local/production environment.

### 2. Zero Secret Exposure
* Environment files containing sensitive credentials (`.env`, `.env.local`, `.env.production`) **MUST NEVER** be committed to version control.
* Sensitive keys (payment gateway secrets, database passwords, session signing keys, webhook secrets) must never be hardcoded into source files or outputted to terminal logs.

---

## 5. Build & Runtime Environment Alignment

* **Development vs. Production Parity**:
  * Ensure that local development behaviors faithfully replicate production constraints (e.g., timezone set to UTC, cookies declared with `Secure` flag on HTTPS).
* **Configuration Drift Prevention**:
  * All runtime configurations must be read through a centralized configuration service or validated schema (e.g., Zod or Pydantic settings) that validates presence and format at application boot time.
  * If a required environment variable is missing, the application must **fail closed** immediately with a clear boot diagnostic rather than running in an insecure default state.

---

## 6. Escalation Protocol for Dependency Needs

If a task assigned by the Project Owner genuinely requires a new package or configuration change:
1. **STOP before editing manifests**.
2. Prepare a Dependency Request containing:
   * **Package Name & Exact Version**: (e.g., `argon2-cffi==23.1.0`).
   * **Specific Purpose**: Which user requirement requires this library?
   * **License & Security Audit**: Confirm permissive open-source license (MIT, Apache 2.0, BSD) and zero known CVE vulnerabilities.
   * **Bundle & Runtime Impact**: Size overhead, performance implications.
   * **Native Alternatives Considered**: Can the problem be solved cleanly with standard libraries or existing packages?
3. Present the request to the Project Owner.
4. Proceed **only** after receiving explicit written authorization.
