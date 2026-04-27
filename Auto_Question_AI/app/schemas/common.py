from typing import Any, Optional
from pydantic import BaseModel


class APIResponse(BaseModel):
    status: str = "success"
    message: str = ""
    data: Optional[Any] = None
