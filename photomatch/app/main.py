from pathlib import Path

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.config import settings
from app.database import Base, engine, get_db
from app.models import User, Project


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

DATA_DIR.mkdir(exist_ok=True)

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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

    except Exception as e:
        db.rollback()
        print("ERROR creating default admin:", str(e))

    finally:
        db.close()


try:
    create_default_admin()
except Exception as e:
    print("STARTUP ERROR creating default admin:", str(e))


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "base_dir": str(BASE_DIR),
        "templates_dir_exists": TEMPLATES_DIR.exists(),
        "static_dir_exists": STATIC_DIR.exists(),
        "data_dir_exists": DATA_DIR.exists()
    }


@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        name="login.html",
        request=request,
        context={
            "app_name": settings.APP_NAME,
            "error": None,
            "user": None
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
            name="login.html",
            request=request,
            context={
                "app_name": settings.APP_NAME,
                "error": "Λάθος email ή κωδικός.",
                "user": None
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

    return db.query(User).filter(User.email == user_email).first()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=302)

    projects = db.query(Project).order_by(Project.created_at.desc()).all()

    return templates.TemplateResponse(
        name="dashboard.html",
        request=request,
        context={
            "app_name": settings.APP_NAME,
            "user": user,
            "projects": projects
        }
    )
