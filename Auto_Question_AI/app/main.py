from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database.base import Base
from app.database.session import engine
import app.models  # noqa: F401  # Ensure all SQLAlchemy models are registered
from app.routers import auth, users, subjects, questions, paper, academic
from app.utils.config import settings
from app.utils.errors import ErrorHandlingMiddleware
from app.utils.response import success_response, error_response

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list(),
    allow_credentials=settings.CORS_ORIGINS != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for generated papers
app.mount("/files", StaticFiles(directory="output"), name="files")

# Routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(subjects.router)
app.include_router(questions.router)
app.include_router(paper.router)
app.include_router(academic.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content=error_response(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content=error_response("Validation error", exc.errors()))


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return success_response({"name": settings.APP_NAME, "env": settings.ENV})
