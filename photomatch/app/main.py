from pathlib import Path

from fastapi import FastAPI, Request, Form, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.config import settings
from app.database import Base, engine, get_db
from app.models import User, Project, Product

import json
import secrets
from app.file_parser import parse_uploaded_file


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

@app.get("/projects/create", response_class=HTMLResponse)
def create_project_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse(
        name="create_project.html",
        request=request,
        context={
            "app_name": settings.APP_NAME,
            "user": user
        }
    )


@app.post("/projects/create")
async def create_project_submit(
    request: Request,
    store_name: str = Form(...),
    store_email: str = Form(None),
    salesforce_grid: str = Form(None),
    product_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # Προσωρινή απλή αποθήκευση αρχείου στο Render filesystem.
    # Στο επόμενο βήμα θα το διαβάζουμε και μετά θα το στέλνουμε Google Drive.
    uploads_dir = DATA_DIR / "uploads"
    uploads_dir.mkdir(exist_ok=True)

    safe_filename = product_file.filename.replace(" ", "_")
    file_path = uploads_dir / safe_filename

    file_bytes = await product_file.read()

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    import secrets

    project_token = secrets.token_urlsafe(12)

    new_project = Project(
        project_token=project_token,
        store_name=store_name,
        store_email=store_email,
        salesforce_grid=salesforce_grid,
        original_filename=product_file.filename,
        status="active",
        created_by=user.id
    )

    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    return RedirectResponse(
        url=f"/projects/{new_project.id}",
        status_code=302
    )


@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail_page(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=302)

    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        return RedirectResponse(url="/dashboard", status_code=302)

    products_count = len(project.products)

    return templates.TemplateResponse(
        name="project_detail.html",
        request=request,
        context={
            "app_name": settings.APP_NAME,
            "user": user,
            "project": project,
            "products_count": products_count
        }
    )

@app.post("/projects/preview", response_class=HTMLResponse)
async def preview_project_file(
    request: Request,
    store_name: str = Form(...),
    store_email: str = Form(None),
    salesforce_grid: str = Form(None),
    product_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=302)

    file_bytes = await product_file.read()

    try:
        parsed = parse_uploaded_file(product_file.filename, file_bytes)
    except Exception as e:
        return templates.TemplateResponse(
            name="create_project.html",
            request=request,
            context={
                "app_name": settings.APP_NAME,
                "user": user,
                "error": str(e)
            }
        )

    temp_dir = DATA_DIR / "temp"
    temp_dir.mkdir(exist_ok=True)

    temp_file_id = secrets.token_urlsafe(12)
    temp_json_path = temp_dir / f"{temp_file_id}.json"
    temp_original_path = temp_dir / f"{temp_file_id}_{product_file.filename.replace(' ', '_')}"

    with open(temp_json_path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, ensure_ascii=False)

    with open(temp_original_path, "wb") as f:
        f.write(file_bytes)

    return templates.TemplateResponse(
        name="preview_project.html",
        request=request,
        context={
            "app_name": settings.APP_NAME,
            "user": user,
            "temp_file_id": temp_file_id,
            "store_name": store_name,
            "store_email": store_email,
            "salesforce_grid": salesforce_grid,
            "original_filename": product_file.filename,
            "columns": parsed["columns"],
            "preview_rows": parsed["preview_rows"],
            "total_rows": parsed["total_rows"]
        }
    )


@app.post("/projects/create/final")
def create_project_final(
    request: Request,
    temp_file_id: str = Form(...),
    store_name: str = Form(...),
    store_email: str = Form(None),
    salesforce_grid: str = Form(None),
    original_filename: str = Form(...),
    barcode_column: str = Form(None),
    item_name_column: str = Form(...),
    sku_column: str = Form(None),
    product_id_column: str = Form(None),
    category_column: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=302)

    temp_json_path = DATA_DIR / "temp" / f"{temp_file_id}.json"

    if not temp_json_path.exists():
        return RedirectResponse(url="/projects/create", status_code=302)

    with open(temp_json_path, "r", encoding="utf-8") as f:
        parsed = json.load(f)

    rows = parsed.get("rows", [])

    project_token = secrets.token_urlsafe(12)

    new_project = Project(
        project_token=project_token,
        store_name=store_name,
        store_email=store_email,
        salesforce_grid=salesforce_grid,
        original_filename=original_filename,
        status="active",
        created_by=user.id
    )

    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    created_products = 0

    for row in rows:
        item_name = str(row.get(item_name_column, "")).strip()

        if not item_name:
            continue

        product = Product(
            project_id=new_project.id,
            barcode=str(row.get(barcode_column, "")).strip() if barcode_column else None,
            item_name=item_name,
            sku=str(row.get(sku_column, "")).strip() if sku_column else None,
            product_id=str(row.get(product_id_column, "")).strip() if product_id_column else None,
            category=str(row.get(category_column, "")).strip() if category_column else None,
            photo_status="missing"
        )

        db.add(product)
        created_products += 1

    db.commit()

    try:
        temp_json_path.unlink()
    except Exception:
        pass

    return RedirectResponse(
        url=f"/projects/{new_project.id}",
        status_code=302
    )

@app.get("/store/{project_token}", response_class=HTMLResponse)
def store_upload_page(
    project_token: str,
    request: Request,
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_token == project_token).first()

    if not project:
        return HTMLResponse(
            content="<h1>Project not found</h1><p>Το link δεν είναι σωστό ή έχει λήξει.</p>",
            status_code=404
        )

    total_products = len(project.products)
    uploaded_products = len([p for p in project.products if p.photo_status in ["uploaded", "approved"]])
    missing_products = len([p for p in project.products if p.photo_status == "missing"])

    return templates.TemplateResponse(
        name="store_upload.html",
        request=request,
        context={
            "app_name": settings.APP_NAME,
            "user": None,
            "project": project,
            "total_products": total_products,
            "uploaded_products": uploaded_products,
            "missing_products": missing_products,
            "message": None
        }
    )


@app.post("/store/{project_token}/products/{product_id}/upload-photo", response_class=HTMLResponse)
async def upload_product_photo(
    project_token: str,
    product_id: int,
    request: Request,
    photo_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.project_token == project_token).first()

    if not project:
        return HTMLResponse(
            content="<h1>Project not found</h1><p>Το link δεν είναι σωστό ή έχει λήξει.</p>",
            status_code=404
        )

    product = db.query(Product).filter(
        Product.id == product_id,
        Product.project_id == project.id
    ).first()

    if not product:
        return HTMLResponse(
            content="<h1>Product not found</h1><p>Το προϊόν δεν βρέθηκε.</p>",
            status_code=404
        )

    photos_dir = DATA_DIR / "uploads" / "photos" / str(project.id)
    photos_dir.mkdir(parents=True, exist_ok=True)

    original_filename = photo_file.filename or "photo.jpg"
    extension = original_filename.split(".")[-1].lower() if "." in original_filename else "jpg"

    safe_barcode = (product.barcode or "no_barcode").replace("/", "_").replace("\\", "_")
    safe_product_id = (product.product_id or str(product.id)).replace("/", "_").replace("\\", "_")

    safe_item_name = product.item_name[:50]
    safe_item_name = "".join(
        c if c.isalnum() or c in [" ", "_", "-"] else "_"
        for c in safe_item_name
    ).strip().replace(" ", "_")

    final_filename = f"{safe_barcode}_{safe_product_id}_{safe_item_name}.{extension}"
    file_path = photos_dir / final_filename

    file_bytes = await photo_file.read()

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    product.photo_status = "uploaded"
    product.photo_filename = final_filename
    product.photo_drive_file_id = None
    product.photo_drive_url = None

    db.commit()

    total_products = len(project.products)
    uploaded_products = len([p for p in project.products if p.photo_status in ["uploaded", "approved"]])
    missing_products = len([p for p in project.products if p.photo_status == "missing"])

    return templates.TemplateResponse(
        name="store_upload.html",
        request=request,
        context={
            "app_name": settings.APP_NAME,
            "user": None,
            "project": project,
            "total_products": total_products,
            "uploaded_products": uploaded_products,
            "missing_products": missing_products,
            "message": f"Η φωτογραφία για το προϊόν '{product.item_name}' ανέβηκε επιτυχώς."
        }
    )
