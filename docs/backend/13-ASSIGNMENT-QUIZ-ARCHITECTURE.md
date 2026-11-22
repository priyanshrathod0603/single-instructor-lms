# Assignments & Quizzes Architecture Specification

## 1. Assignment Management & Rubric Grading

Assignments allow students to submit project work (PDF portfolios, code archives, design assets) evaluated against structured rubrics.

```mermaid
stateDiagram-v2
    [*] --> Draft_Assignment : Instructor Configures Rubric
    Draft_Assignment --> Active_Assignment : Lesson Published
    
    Active_Assignment --> Submitted : Student Uploads Submission
    Submitted --> In_Grading : Staff Begins Evaluation
    In_Grading --> Graded : Rubric Criteria Scored
    Graded --> Overridden : Super Admin Overrides Score
    Graded --> [*] : Grade Released to Student
```

### 1.1 Rubric Criteria & Weighting Model
A rubric is composed of multiple evaluation criteria:
$$\text{Final Score} = \sum_{i=1}^{k} \big( \text{points\_awarded}_i \times \text{weight}_i \big)$$

* **Criteria Immutability**: Once any student submission has been evaluated against a rubric, that rubric version is permanently frozen (`is_active = FALSE` for future edits). Modifying the rubric spawns a new version (`version = V + 1`).
* **Evaluation Workflow**: Staff and Admins review the submission file, award points per criterion in `rubric_scores`, and provide qualitative commentary.
* **Super Admin Grade Overrides**: If an instructor adjusts a grade following a student appeal, the change is recorded in `grade_overrides` with the original score, new score, timestamp, and mandatory justification note.

---

## 2. Quizzes & Question Banks

Quizzes provide automated, objective assessment of learner comprehension with server-authoritative timers and randomized delivery.

### 2.1 Question Formats
1. `MCQ_SINGLE`: Single-choice multiple question with exactly one correct option.
2. `MCQ_MULTI`: Multi-select question (partial credit or all-or-nothing evaluation).
3. `TRUE_FALSE`: Binary truth evaluation.
4. `TEXT_SHORT`: Case-insensitive exact match or regex evaluation for short keywords.

### 2.2 Bulk CSV Question Import Specification
Instructors can upload question banks via CSV (`POST /api/v1/quizzes/{id}/questions/bulk-csv`):

```csv
question_type,prompt,points,explanation,option_1,option_2,option_3,option_4,correct_options
MCQ_SINGLE,"What does ACID stand for?",1.0,"ACID is Atomicity, Consistency, Isolation, Durability","Atomicity Consistency Isolation Durability","All Cats In Denmark","Async Code In Django","Access Control Identity Domain","1"
MCQ_MULTI,"Which are valid HTTP status codes?",2.0,"200 and 404 are valid codes","200 OK","404 Not Found","999 Custom","701 Test","1,2"
TRUE_FALSE,"PostgreSQL partial indexes improve write performance.",1.0,"Partial indexes index only a subset of rows, reducing index size.","True","False","","","1"
```

---

## 3. Server-Authoritative Quiz Timer & Autosave Engine

Client-side clocks cannot be trusted for timed assessments. The backend enforces an immutable server timer.

```mermaid
sequenceDiagram
    autonumber
    actor Student
    participant Browser
    participant API as FastAPI Backend
    participant DB as PostgreSQL

    Student->>Browser: Click "Start Quiz"
    Browser->>API: POST /api/v1/quizzes/{id}/attempts
    API->>DB: Check max_attempts constraint
    API->>DB: INSERT INTO quiz_attempts (started_at=NOW(), status='IN_PROGRESS')
    API->>API: Calculate deadline: started_at + time_limit_minutes
    API-->>Browser: { "attempt_id": "...", "questions": [...], "server_deadline": "2026-11-13T22:30:00Z" }

    loop During Attempt (Every 30s or on selection)
        Browser->>API: PATCH /api/v1/quiz-attempts/{id}/autosave { "question_id": "...", "selected_options": [...] }
        API->>DB: UPSERT INTO quiz_answers (attempt_id, question_id, selected_option_ids, autosaved_at=NOW())
        API-->>Browser: { "saved": true }
    end

    Student->>Browser: Click "Submit Quiz"
    Browser->>API: POST /api/v1/quiz-attempts/{id}/submit
    API->>API: Verify NOW() <= server_deadline + 30s grace window
    alt Within Deadline
        API->>DB: Calculate score & compare with pass_percentage
        API->>DB: UPDATE quiz_attempts SET status='SUBMITTED', score=85.0, is_passed=TRUE
        API-->>Browser: { "status": "SUBMITTED", "score": 85.0, "is_passed": true }
    else Expired
        API->>DB: UPDATE quiz_attempts SET status='EXPIRED', score=0, is_passed=FALSE
        API-->>Browser: { "status": "EXPIRED", "message": "Time limit exceeded" }
    end
```

### 3.1 Network Latency Grace Window
A 30-second server grace period (`grace_window = 30 seconds`) is added to `time_limit_minutes` to account for client network jitter without penalizing students. Submissions received after `started_at + time_limit_minutes + 30s` are marked `EXPIRED`.
