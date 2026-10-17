from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import (DUMMY_HASH, current_user, end_session, hash_password, require_user,
                    start_session, utcnow, verify_password)
from ..db import get_db
from ..models import Pitcher, User
from ..photos import remove_photo
from ..schemas import LoginIn, SignupIn, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(body: SignupIn, response: Response, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with that email already exists")
    user = User(email=email, display_name=body.display_name.strip(),
                password_hash=hash_password(body.password), created_at=utcnow())
    db.add(user)
    db.commit()
    start_session(db, user, response)
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    # always run one hash so unknown emails take as long as wrong passwords
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not (user and ok):
        raise HTTPException(401, "Invalid email or password")
    start_session(db, user, response)
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    end_session(db, request, response)


@router.get("/me", response_model=UserOut | None)
def me(user: User | None = Depends(current_user)):
    """The signed-in user, or null."""
    return user


@router.delete("/me", status_code=204)
def delete_account(request: Request, response: Response, user: User = Depends(require_user),
                   db: Session = Depends(get_db)):
    """Delete the account and everything it owns (private pitchers, goals, tracking)."""
    end_session(db, request, response)
    for pitcher in db.scalars(select(Pitcher).where(Pitcher.owner_id == user.id)).all():
        remove_photo(pitcher)
        db.delete(pitcher)  # ORM cascade removes their games and pitches
    db.flush()  # pitchers must go before the user row they reference
    db.delete(user)  # goals, tracking and sessions cascade in the database
    db.commit()
