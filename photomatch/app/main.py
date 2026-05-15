import os
from pathlib import Path

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.config import settings
from app.database import Base, engine, get_db
from app.models import User, Project, Product


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_default_admin():
    db = next(get_db())

    try:
        existing_user = db.query(User).filter(User.email == settings.ADMIN_EMAIL).first()

        if existing_user:
            return

        admin_user = User(
            email=settings.ADMIN_EMAIL,
            name=settings.ADMIN_NAME,
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            role="admin"
        )

        db.add(admin_user)
        db.commit()

    finally:
        db.close()


create_default_admin()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV
    }


@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "error": None
        }
    )


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "error": "Λάθος email ή κωδικός."
            }
        )

    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key="photomatch_user_email",
        value=user.email,
        httponly=True,
        max_age=60 * 60 * 8
    )
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("photomatch_user_email")
    return response


def get_current_user(request: Request, db: Session):
    user_email = request.cookies.get("photomatch_user_email")

    if not user_email:
        return None

    user = db.query(User).filter(User.email == user_email).first()
    return user


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=302)

    projects = db.query(Project).order_by(Project.created_at.desc()).all()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "projects": projects
        }
    )
