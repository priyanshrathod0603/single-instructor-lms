"""Quiz repository implementing database queries for quizzes, questions, attempts, and answers.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 4, Tables 20-24)
- docs/backend/13-ASSIGNMENT-QUIZ-ARCHITECTURE.md (Sections 2, 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK801-TASK805)
"""

from datetime import datetime
from typing import Any, List, Optional, Sequence, Tuple
import uuid

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.base import utc_now
from app.models.quiz import (
    ATTEMPT_STATUS_IN_PROGRESS,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
    QuizQuestionOption,
)


class QuizRepository:
    """Repository handling persistence operations for quizzes and question banks."""

    def get_quiz_by_id(
        self,
        session: Session,
        quiz_id: uuid.UUID,
        for_update: bool = False,
    ) -> Optional[Quiz]:
        """Fetch quiz by UUID with optional row-level lock."""
        stmt = (
            select(Quiz)
            .options(
                selectinload(Quiz.questions).selectinload(QuizQuestion.options)
            )
            .filter(Quiz.id == quiz_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return session.execute(stmt).scalar_one_or_none()

    def get_quiz_by_lesson_id(
        self,
        session: Session,
        lesson_id: uuid.UUID,
    ) -> Optional[Quiz]:
        """Fetch quiz attached to a curriculum lesson."""
        stmt = (
            select(Quiz)
            .options(
                selectinload(Quiz.questions).selectinload(QuizQuestion.options)
            )
            .filter(Quiz.lesson_id == lesson_id)
        )
        return session.execute(stmt).scalar_one_or_none()

    def create_quiz(
        self,
        session: Session,
        lesson_id: uuid.UUID,
        title: str,
        description: Optional[str] = None,
        pass_percentage: int = 70,
        time_limit_minutes: int = 30,
        shuffle_questions: bool = True,
        max_attempts: int = 3,
    ) -> Quiz:
        """Create a new quiz configuration attached to a lesson."""
        quiz = Quiz(
            lesson_id=lesson_id,
            title=title,
            description=description,
            pass_percentage=pass_percentage,
            time_limit_minutes=time_limit_minutes,
            shuffle_questions=shuffle_questions,
            max_attempts=max_attempts,
        )
        session.add(quiz)
        session.flush()
        return quiz

    def update_quiz(
        self,
        session: Session,
        quiz: Quiz,
        title: Optional[str] = None,
        description: Optional[str] = None,
        pass_percentage: Optional[int] = None,
        time_limit_minutes: Optional[int] = None,
        shuffle_questions: Optional[bool] = None,
        max_attempts: Optional[int] = None,
    ) -> Quiz:
        """Update existing quiz parameters."""
        if title is not None:
            quiz.title = title
        if description is not None:
            quiz.description = description
        if pass_percentage is not None:
            quiz.pass_percentage = pass_percentage
        if time_limit_minutes is not None:
            quiz.time_limit_minutes = time_limit_minutes
        if shuffle_questions is not None:
            quiz.shuffle_questions = shuffle_questions
        if max_attempts is not None:
            quiz.max_attempts = max_attempts
        quiz.updated_at = utc_now()
        session.flush()
        return quiz

    def add_question(
        self,
        session: Session,
        quiz_id: uuid.UUID,
        question_type: str,
        prompt: str,
        points: float = 1.0,
        explanation: Optional[str] = None,
        sort_order: int = 0,
    ) -> QuizQuestion:
        """Add a question to a quiz."""
        question = QuizQuestion(
            quiz_id=quiz_id,
            question_type=question_type,
            prompt=prompt,
            points=points,
            explanation=explanation,
            sort_order=sort_order,
        )
        session.add(question)
        session.flush()
        return question

    def add_question_option(
        self,
        session: Session,
        question_id: uuid.UUID,
        option_text: str,
        is_correct: bool = False,
        sort_order: int = 0,
    ) -> QuizQuestionOption:
        """Add an answer option to a question."""
        option = QuizQuestionOption(
            question_id=question_id,
            option_text=option_text,
            is_correct=is_correct,
            sort_order=sort_order,
        )
        session.add(option)
        session.flush()
        return option

    def get_questions_for_quiz(
        self,
        session: Session,
        quiz_id: uuid.UUID,
    ) -> List[QuizQuestion]:
        """Fetch all questions with options for a quiz ordered by sort_order."""
        stmt = (
            select(QuizQuestion)
            .options(selectinload(QuizQuestion.options))
            .filter(QuizQuestion.quiz_id == quiz_id)
            .order_by(QuizQuestion.sort_order.asc(), QuizQuestion.id.asc())
        )
        return list(session.execute(stmt).scalars().all())

    def get_latest_attempt_no(
        self,
        session: Session,
        quiz_id: uuid.UUID,
        student_id: uuid.UUID,
    ) -> int:
        """Get the highest attempt_no recorded for student on a quiz."""
        stmt = (
            select(func.max(QuizAttempt.attempt_no))
            .filter(
                QuizAttempt.quiz_id == quiz_id,
                QuizAttempt.student_id == student_id,
            )
        )
        val = session.execute(stmt).scalar()
        return val if val is not None else 0

    def get_in_progress_attempt(
        self,
        session: Session,
        quiz_id: uuid.UUID,
        student_id: uuid.UUID,
    ) -> Optional[QuizAttempt]:
        """Find any current IN_PROGRESS attempt for a student on a quiz."""
        stmt = (
            select(QuizAttempt)
            .options(
                joinedload(QuizAttempt.quiz),
                selectinload(QuizAttempt.answers),
            )
            .filter(
                QuizAttempt.quiz_id == quiz_id,
                QuizAttempt.student_id == student_id,
                QuizAttempt.status == ATTEMPT_STATUS_IN_PROGRESS,
            )
            .order_by(QuizAttempt.attempt_no.desc())
        )
        return session.execute(stmt).scalars().first()

    def count_attempts(
        self,
        session: Session,
        quiz_id: uuid.UUID,
        student_id: uuid.UUID,
    ) -> int:
        """Count total attempts made by student on a quiz."""
        stmt = (
            select(func.count(QuizAttempt.id))
            .filter(
                QuizAttempt.quiz_id == quiz_id,
                QuizAttempt.student_id == student_id,
            )
        )
        return session.execute(stmt).scalar() or 0

    def create_attempt(
        self,
        session: Session,
        quiz_id: uuid.UUID,
        student_id: uuid.UUID,
        attempt_no: int,
        started_at: Optional[datetime] = None,
    ) -> QuizAttempt:
        """Create a new quiz attempt session."""
        attempt = QuizAttempt(
            quiz_id=quiz_id,
            student_id=student_id,
            attempt_no=attempt_no,
            started_at=started_at or utc_now(),
            status=ATTEMPT_STATUS_IN_PROGRESS,
        )
        session.add(attempt)
        session.flush()
        return attempt

    def get_attempt_by_id(
        self,
        session: Session,
        attempt_id: uuid.UUID,
        for_update: bool = False,
    ) -> Optional[QuizAttempt]:
        """Fetch attempt by ID with related quiz and answers."""
        stmt = (
            select(QuizAttempt)
            .options(
                joinedload(QuizAttempt.quiz),
                joinedload(QuizAttempt.student),
                selectinload(QuizAttempt.answers).joinedload(QuizAnswer.question),
            )
            .filter(QuizAttempt.id == attempt_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return session.execute(stmt).scalar_one_or_none()

    def upsert_answer(
        self,
        session: Session,
        attempt_id: uuid.UUID,
        question_id: uuid.UUID,
        selected_option_ids: Optional[List[str]] = None,
        text_response: Optional[str] = None,
    ) -> QuizAnswer:
        """UPSERT an autosaved answer for an attempt and question."""
        stmt = (
            select(QuizAnswer)
            .filter(
                QuizAnswer.attempt_id == attempt_id,
                QuizAnswer.question_id == question_id,
            )
        )
        answer = session.execute(stmt).scalar_one_or_none()

        if answer:
            answer.selected_option_ids = selected_option_ids
            answer.text_response = text_response
            answer.autosaved_at = utc_now()
        else:
            answer = QuizAnswer(
                attempt_id=attempt_id,
                question_id=question_id,
                selected_option_ids=selected_option_ids,
                text_response=text_response,
                autosaved_at=utc_now(),
            )
            session.add(answer)

        session.flush()
        return answer

    def get_answers_for_attempt(
        self,
        session: Session,
        attempt_id: uuid.UUID,
    ) -> List[QuizAnswer]:
        """Fetch all recorded answers for an attempt."""
        stmt = (
            select(QuizAnswer)
            .options(joinedload(QuizAnswer.question))
            .filter(QuizAnswer.attempt_id == attempt_id)
        )
        return list(session.execute(stmt).scalars().all())

    def list_attempts_for_quiz(
        self,
        session: Session,
        quiz_id: uuid.UUID,
        student_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[QuizAttempt], int]:
        """List paginated attempts for a quiz with optional student and status filters."""
        stmt = select(QuizAttempt).filter(QuizAttempt.quiz_id == quiz_id)
        count_stmt = select(func.count(QuizAttempt.id)).filter(QuizAttempt.quiz_id == quiz_id)

        if student_id:
            stmt = stmt.filter(QuizAttempt.student_id == student_id)
            count_stmt = count_stmt.filter(QuizAttempt.student_id == student_id)
        if status:
            stmt = stmt.filter(QuizAttempt.status == status)
            count_stmt = count_stmt.filter(QuizAttempt.status == status)

        total = session.execute(count_stmt).scalar() or 0
        items = list(
            session.execute(
                stmt.options(joinedload(QuizAttempt.student), joinedload(QuizAttempt.quiz))
                .order_by(QuizAttempt.started_at.desc())
                .offset(skip)
                .limit(limit)
            ).scalars().all()
        )
        return items, total

    def list_attempts_for_student(
        self,
        session: Session,
        student_id: uuid.UUID,
        quiz_id: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[QuizAttempt], int]:
        """List paginated attempts for a specific student."""
        stmt = select(QuizAttempt).filter(QuizAttempt.student_id == student_id)
        count_stmt = select(func.count(QuizAttempt.id)).filter(QuizAttempt.student_id == student_id)

        if quiz_id:
            stmt = stmt.filter(QuizAttempt.quiz_id == quiz_id)
            count_stmt = count_stmt.filter(QuizAttempt.quiz_id == quiz_id)

        total = session.execute(count_stmt).scalar() or 0
        items = list(
            session.execute(
                stmt.options(joinedload(QuizAttempt.quiz))
                .order_by(QuizAttempt.started_at.desc())
                .offset(skip)
                .limit(limit)
            ).scalars().all()
        )
        return items, total
