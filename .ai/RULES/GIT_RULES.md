# Version Control & Git Governance Rules (GIT_RULES)

## 1. Git Authority & History Preservation

This document governs all interactions with the Git version control system, branch structures, working tree states, and commit workflows for the Single-Instructor LMS.

**The Golden Version Control Principle**:
Git history is the immutable, authoritative record of physical code changes. The AI agent operates as a contributor, **NOT** the repository owner. Under no circumstances may an AI agent destroy, overwrite, or rewrite version control history without explicit written owner authorization.

All Git operations must strictly adhere to the universal directives in [.ai/RULES/GLOBAL_RULES.md](file:///Users/priyansh/lms/.ai/RULES/GLOBAL_RULES.md).

---

## 2. Absolute Prohibitions (Zero Destructive Git Operations)

The AI agent is **STRICTLY PROHIBITED** from executing any of the following commands without explicit written approval:
* **NEVER** execute `git commit` unless explicitly instructed to commit by the Project Owner.
* **NEVER** execute `git push` or `git push --force`.
* **NEVER** execute hard working-tree resets (`git reset --hard`).
* **NEVER** execute untracked file purges (`git clean -f`, `git clean -fd`).
* **NEVER** discard modified or uncommitted files (`git checkout -- .`, `git restore .`).
* **NEVER** rewrite commit history (`git rebase`, `git rebase -i`, `git commit --amend`).
* **NEVER** delete local or remote branches (`git branch -D`, `git push origin --delete`).
* **NEVER** merge branches (`git merge`) or resolve merge conflicts unilaterally.

---

## 3. Working Tree Protection & Pre-Task Inspection

### Mandatory Pre-Task Git Inspection:
Before creating or modifying any file, the AI agent **MUST**:
1. Check the repository status (`git status`).
2. Identify whether untracked files or uncommitted modifications exist.
3. If uncommitted modifications exist that are unrelated to the current task:
   * **DO NOT DISCARD OR OVERWRITE THEM**.
   * Assume all uncommitted work belongs to the Project Owner or a concurrent session.
   * Confine your changes strictly to the files authorized for the active task.

---

## 4. Verification via Git Diff

Before reporting any engineering task as complete:
1. Run `git diff` on all modified files.
2. Verify that:
   * Only the files authorized for the task have been altered.
   * No debug statements (`console.log`, `print()`, `debugger;`) remain.
   * No secrets, API keys, or environment tokens have been committed to code.
   * No whitespace thrashing or unrelated formatting re-indentations were applied.

---

## 5. Relationship Between Git and `.ai/` Tracking

* **Git as Source of Code Truth**: Physical code changes, line deltas, and file creations are recorded by Git.
* **`.ai/` as Architectural Context & Explanation**: The tracking files ([.ai/TRACKING/CHANGELOG.md](file:///Users/priyansh/lms/.ai/TRACKING/CHANGELOG.md), [.ai/TRACKING/AUDIT_LOG.md](file:///Users/priyansh/lms/.ai/TRACKING/AUDIT_LOG.md), etc.) provide human-readable architectural summaries, justification reasons, and cross-references.
* The `.ai/` tracking files **supplement** Git; they do not replace Git commits.
