from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import datetime


class QuestionCreate(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Question cannot be empty.")
        return v.strip()


class AnswerCreate(BaseModel):
    answer: str

    @field_validator("answer")
    @classmethod
    def answer_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Answer cannot be empty.")
        return v.strip()


class QuestionOut(BaseModel):
    id: UUID
    question: str
    answer: str | None
    asker_name: str
    created_at: datetime
    answered_at: datetime | None

    class Config:
        from_attributes = True