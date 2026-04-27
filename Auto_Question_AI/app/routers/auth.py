from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.schemas.user import UserCreate, UserLogin, UserOut
from app.schemas.auth import Token
from app.services.auth_service import create_user, authenticate_user
from app.models.user import User
from app.utils.deps import get_db
from app.utils.response import success_response
from app.utils.security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
    user = create_user(db, payload.username, payload.password, payload.role or "student", payload.email)
    return success_response(UserOut.model_validate(user).model_dump(), "User registered")


@router.post("/login")
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": user.username})
    return success_response(Token(access_token=token).model_dump(), "Login successful")
