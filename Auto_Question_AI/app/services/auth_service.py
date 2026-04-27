from sqlalchemy.orm import Session

from app.models.user import User
from app.utils.security import hash_password, verify_password


def create_user(db: Session, username: str, password: str, role: str, email: str | None = None) -> User:
    user = User(username=username, email=email, hashed_password=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
