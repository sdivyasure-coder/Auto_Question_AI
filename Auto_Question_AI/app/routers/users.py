from fastapi import APIRouter, Depends

from app.schemas.user import UserOut
from app.utils.deps import get_current_user
from app.utils.response import success_response

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def me(user=Depends(get_current_user)):
    return success_response(UserOut.model_validate(user).model_dump(), "Current user")
