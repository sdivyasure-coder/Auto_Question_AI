from typing import Any


def success_response(data: Any = None, message: str = "") -> dict:
    return {"status": "success", "message": message, "data": data}


def error_response(message: str = "", data: Any = None) -> dict:
    return {"status": "error", "message": message, "data": data}
