from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin, get_db
from app.models.user import User
from app.models.product import Product
from app.models.question import ProductQuestion
from app.schemas.question import QuestionCreate, AnswerCreate, QuestionOut
from app.services.notification_service import notify_admins_new_question, notify_buyer_question_answered

router = APIRouter(prefix="/products", tags=["questions"])


def _to_out(q: ProductQuestion) -> QuestionOut:
    return QuestionOut(
        id=q.id,
        question=q.question,
        answer=q.answer,
        asker_name=(q.user.full_name or q.user.email.split("@")[0]) if q.user else "Buyer",
        created_at=q.created_at,
        answered_at=q.answered_at,
    )


@router.get("/{product_id}/questions", response_model=list[QuestionOut])
def list_questions(product_id: str, db: Session = Depends(get_db)):
    questions = (
        db.query(ProductQuestion)
        .filter(ProductQuestion.product_id == product_id)
        .order_by(ProductQuestion.created_at.desc())
        .all()
    )
    return [_to_out(q) for q in questions]


@router.post("/{product_id}/questions", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
def ask_question(
    product_id: str,
    data: QuestionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")

    question = ProductQuestion(product_id=product_id, user_id=user.id, question=data.question)
    db.add(question)
    db.commit()
    db.refresh(question)

    try:
        notify_admins_new_question(db, question, product.title)
    except Exception as e:
        print(f"[questions] Admin notification failed for question {question.id}: {e}")

    return _to_out(question)


@router.patch("/{product_id}/questions/{question_id}/answer", response_model=QuestionOut)
def answer_question(
    product_id: str,
    question_id: str,
    data: AnswerCreate,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    question = (
        db.query(ProductQuestion)
        .filter(ProductQuestion.id == question_id, ProductQuestion.product_id == product_id)
        .first()
    )
    if not question:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found.")

    product = db.query(Product).filter(Product.id == product_id).first()

    question.answer = data.answer
    question.answered_at = datetime.utcnow()
    db.commit()
    db.refresh(question)

    try:
        notify_buyer_question_answered(db, question, product.title if product else "your item")
    except Exception as e:
        print(f"[questions] Buyer notification failed for question {question.id}: {e}")

    return _to_out(question)