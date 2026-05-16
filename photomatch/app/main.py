from pathlib import Path
import json
import secrets
import re

from fastapi import FastAPI, Request, Form, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.config import settings
from app.database import Base, engine, get_db
from app.models import User, Project, Product
from app.file_parser import parse_uploaded_file
from app.drive_service import (
    create_folder,
    upload_bytes_to_drive,
    make_file_public,
    safe_drive_folder_name
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = DATA_DIR / "temp"
UPLOADS_DIR = DATA_DIR / "uploads"
PHOTOS_DIR = UPLOADS_DIR / "photos"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

DATA_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# APP SETUP
# ============================================================

app = FastAPI(title=settings.APP_NAME)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============================================================
# SECURITY HELPERS
# ============================================================

COOKIE_NAME = "photomatch_user_email"
COOKIE_MAX_AGE = 60 * 60 * 8  # 8 hours

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def login_redirect():
    return RedirectResponse(url="/login", status_code=302)


def dashboard_redirect():
    return RedirectResponse(url="/dashboard", status_code=302)


def get_current_user(request: Request, db: Session):
    user_email = request.cookies.get(COOKIE_NAME)

    if not user_email:
        return None

    return db.query(User).filter(User.email == user_email).first()


def sanitize_filename_part(value: str, max_length: int = 80) -> str:
    if not value:
        return "unknown"

    value = str(value).strip()
    value = value[:max_length]
    value = re.sub(r"[^\w\s\-Α-Ωα-ωΆ-Ώά-ώ]", "_", value, flags=re.UNICODE)
    value = re.sub(r"\s+", "_", value)
    value = value.strip("_")

    return value or "unknown"


def get_file_extension(filename: str, default: str = "jpg") -> str:
    if not filename or "." not in filename:
        return default

    return filename.rsplit(".", 1)[-1].lower().strip()


def count_project_products(db: Session, project_id: int):
    total = db.query(Product).filter(Product.project_id == project_id).count()

    uploaded = db.query(Product).filter(
        Product.project_id == project_id,
        Product.photo_status.in_(["uploaded", "approved"])
    ).count()

    missing = db.query(Product).filter(
        Product.project_id == project_id,
        Product.photo_status == "missing"
    ).count()

    return total, uploaded, missing


# ============================================================
# DATABASE STARTUP
# ============================================================

def create_default_admin():
    db_generator = get_db()
    db = next(db_generator)

    try:
        existing_user = db.query(User).filter(
            User.email == settings.ADMIN_EMAIL
        ).first()

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

        print("Default admin created:", settings.ADMIN_EMAIL)

    except Exception as e:
        db.rollback()
        print("ERROR creating default admin:", str(e))

    finally:
        try:
            db_generator.close()
        except Exception:
            pass


@app.on_event("startup")
def startup_event():
    try:
        Base.metadata.create_all(bind=engine)
        create_default_admin()
    except Exception as e:
        print("STARTUP ERROR:", str(e))


# ============================================================
# HEALTH
# ============================================================

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


# ============================================================
# AUTH ROUTES
# ============================================================

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
    user = db.query(User).filter(User.email == email.strip()).first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "error": "Λάθος email ή κωδικός.",
                "user": None
            }
        )

    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=user.email,
        httponly=True,
        max_age=COOKIE_MAX_AGE,
        samesite="lax"
    )

    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ============================================================
# ADMIN / DASHBOARD
# ============================================================

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)

    if not user:
        return login_redirect()

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


@app.get("/projects/create", response_class=HTMLResponse)
def create_project_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)

    if not user:
        return login_redirect()

    return templates.TemplateResponse(
        "create_project.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "error": None
        }
    )


# ============================================================
# PROJECT PREVIEW
# ============================================================

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
        return login_redirect()

    if not product_file.filename:
        return templates.TemplateResponse(
            "create_project.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "user": user,
                "error": "Δεν επιλέχθηκε αρχείο."
            }
        )

    file_bytes = await product_file.read()

    if not file_bytes:
        return templates.TemplateResponse(
            "create_project.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "user": user,
                "error": "Το αρχείο είναι κενό."
            }
        )

    try:
        parsed = parse_uploaded_file(product_file.filename, file_bytes)
    except Exception as e:
        return templates.TemplateResponse(
            "create_project.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "user": user,
                "error": str(e)
            }
        )

    temp_file_id = secrets.token_urlsafe(12)
    safe_original_name = sanitize_filename_part(product_file.filename, max_length=120)

    temp_json_path = TEMP_DIR / f"{temp_file_id}.json"
    temp_original_path = TEMP_DIR / f"{temp_file_id}_{safe_original_name}"

    with open(temp_json_path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, ensure_ascii=False)

    with open(temp_original_path, "wb") as f:
        f.write(file_bytes)

    return templates.TemplateResponse(
        "preview_project.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "temp_file_id": temp_file_id,
            "store_name": store_name,
            "store_email": store_email,
            "salesforce_grid": salesforce_grid,
            "original_filename": product_file.filename,
            "columns": parsed.get("columns", []),
            "preview_rows": parsed.get("preview_rows", []),
            "total_rows": parsed.get("total_rows", 0)
        }
    )


# ============================================================
# CREATE PROJECT FINAL
# ============================================================

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
        return login_redirect()

    temp_json_path = TEMP_DIR / f"{temp_file_id}.json"

    if not temp_json_path.exists():
        return templates.TemplateResponse(
            "create_project.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "user": user,
                "error": "Το προσωρινό αρχείο δεν βρέθηκε. Ανέβασε ξανά το αρχείο."
            }
        )

    with open(temp_json_path, "r", encoding="utf-8") as f:
        parsed = json.load(f)

    rows = parsed.get("rows", [])

    if not rows:
        return templates.TemplateResponse(
            "create_project.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "user": user,
                "error": "Δεν βρέθηκαν προϊόντα στο αρχείο."
            }
        )

    project_token = secrets.token_urlsafe(16)

    drive_folder_id = None
    drive_folder_url = None

    try:
        folder_name = safe_drive_folder_name(store_name, salesforce_grid)
        drive_folder = create_folder(folder_name)

        drive_folder_id = drive_folder.get("id")
        drive_folder_url = drive_folder.get("webViewLink")

    except Exception as e:
        print("ERROR creating Drive folder:", str(e))

    new_project = Project(
        project_token=project_token,
        store_name=store_name.strip(),
        store_email=store_email.strip() if store_email else None,
        salesforce_grid=salesforce_grid.strip() if salesforce_grid else None,
        original_filename=original_filename,
        drive_folder_id=drive_folder_id,
        drive_folder_url=drive_folder_url,
        status="active",
        created_by=user.id
    )

    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    # Upload original Excel/CSV to Drive folder
    try:
        matching_files = list(TEMP_DIR.glob(f"{temp_file_id}_*"))

        if matching_files and new_project.drive_folder_id:
            original_path = matching_files[0]

            with open(original_path, "rb") as f:
                original_bytes = f.read()

            uploaded_original = upload_bytes_to_drive(
                file_bytes=original_bytes,
                filename=original_filename,
                mime_type="application/octet-stream",
                folder_id=new_project.drive_folder_id
            )

            print("Original file uploaded to Drive:", uploaded_original.get("webViewLink"))

    except Exception as e:
        print("ERROR uploading original file to Drive:", str(e))

    created_products = 0

    for row in rows:
        item_name = str(row.get(item_name_column, "")).strip()

        if not item_name:
            continue

        barcode = str(row.get(barcode_column, "")).strip() if barcode_column else None
        sku = str(row.get(sku_column, "")).strip() if sku_column else None
        product_id_value = str(row.get(product_id_column, "")).strip() if product_id_column else None
        category = str(row.get(category_column, "")).strip() if category_column else None

        product = Product(
            project_id=new_project.id,
            barcode=barcode or None,
            item_name=item_name,
            sku=sku or None,
            product_id=product_id_value or None,
            category=category or None,
            photo_status="missing"
        )

        db.add(product)
        created_products += 1

    db.commit()

    print(f"Created project {new_project.id} with {created_products} products.")

    # Cleanup temp files
    try:
        temp_json_path.unlink(missing_ok=True)

        for temp_file in TEMP_DIR.glob(f"{temp_file_id}_*"):
            temp_file.unlink(missing_ok=True)

    except Exception as e:
        print("ERROR cleaning temp files:", str(e))

    return RedirectResponse(
        url=f"/projects/{new_project.id}",
        status_code=302
    )


# ============================================================
# PROJECT DETAIL
# ============================================================

@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail_page(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)

    if not user:
        return login_redirect()

    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        return dashboard_redirect()

    products_count = db.query(Product).filter(Product.project_id == project.id).count()

    return templates.TemplateResponse(
        "project_detail.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": user,
            "project": project,
            "products_count": products_count
        }
    )


# ============================================================
# STORE PUBLIC UPLOAD PAGE
# ============================================================

@app.get("/store/{project_token}", response_class=HTMLResponse)
def store_upload_page(
    project_token: str,
    request: Request,
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(
        Project.project_token == project_token
    ).first()

    if not project:
        return HTMLResponse(
            content="<h1>Project not found</h1><p>Το link δεν είναι σωστό ή έχει λήξει.</p>",
            status_code=404
        )

    total_products, uploaded_products, missing_products = count_project_products(db, project.id)

    return templates.TemplateResponse(
        "store_upload.html",
        {
            "request": request,
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
    project = db.query(Project).filter(
        Project.project_token == project_token
    ).first()

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

    original_filename = photo_file.filename or "photo.jpg"
    extension = get_file_extension(original_filename)

    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        total_products, uploaded_products, missing_products = count_project_products(db, project.id)

        return templates.TemplateResponse(
            "store_upload.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "user": None,
                "project": project,
                "total_products": total_products,
                "uploaded_products": uploaded_products,
                "missing_products": missing_products,
                "message": "Επιτρέπονται μόνο εικόνες JPG, JPEG, PNG ή WEBP."
            }
        )

    file_bytes = await photo_file.read()

    if not file_bytes:
        total_products, uploaded_products, missing_products = count_project_products(db, project.id)

        return templates.TemplateResponse(
            "store_upload.html",
            {
                "request": request,
                "app_name": settings.APP_NAME,
                "user": None,
                "project": project,
                "total_products": total_products,
                "uploaded_products": uploaded_products,
                "missing_products": missing_products,
                "message": "Το αρχείο φωτογραφίας είναι κενό."
            }
        )

    project_photos_dir = PHOTOS_DIR / str(project.id)
    project_photos_dir.mkdir(parents=True, exist_ok=True)

    safe_barcode = sanitize_filename_part(product.barcode or "no_barcode", max_length=60)
    safe_product_id = sanitize_filename_part(product.product_id or str(product.id), max_length=60)
    safe_item_name = sanitize_filename_part(product.item_name, max_length=80)

    final_filename = f"{safe_barcode}_{safe_product_id}_{safe_item_name}.{extension}"
    file_path = project_photos_dir / final_filename

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    drive_file_id = None
    drive_file_url = None

    try:
        if project.drive_folder_id:
            uploaded_drive_file = upload_bytes_to_drive(
                file_bytes=file_bytes,
                filename=final_filename,
                mime_type=photo_file.content_type or "image/jpeg",
                folder_id=project.drive_folder_id
            )

            drive_file_id = uploaded_drive_file.get("id")
            drive_file_url = uploaded_drive_file.get("webViewLink")

            if drive_file_id:
                try:
                    make_file_public(drive_file_id)
                except Exception as permission_error:
                    print("ERROR making Drive file public:", str(permission_error))

    except Exception as e:
        print("ERROR uploading photo to Drive:", str(e))

    product.photo_status = "uploaded"
    product.photo_filename = final_filename
    product.photo_drive_file_id = drive_file_id
    product.photo_drive_url = drive_file_url

    db.commit()

    total_products, uploaded_products, missing_products = count_project_products(db, project.id)

    return templates.TemplateResponse(
        "store_upload.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "user": None,
            "project": project,
            "total_products": total_products,
            "uploaded_products": uploaded_products,
            "missing_products": missing_products,
            "message": f"Η φωτογραφία για το προϊόν '{product.item_name}' ανέβηκε επιτυχώς."
        }
    )


# ============================================================
# ADMIN PHOTO APPROVAL
# ============================================================

@app.post("/admin/products/{product_id}/approve")
def approve_product_photo(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)

    if not user:
        return login_redirect()

    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        return dashboard_redirect()

    product.photo_status = "approved"
    product.reject_reason = None

    db.commit()

    return RedirectResponse(
        url=f"/projects/{product.project_id}",
        status_code=302
    )


@app.post("/admin/products/{product_id}/reject")
def reject_product_photo(
    product_id: int,
    request: Request,
    reject_reason: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)

    if not user:
        return login_redirect()

    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        return dashboard_redirect()

    product.photo_status = "rejected"
    product.reject_reason = reject_reason or "Η φωτογραφία χρειάζεται επανάληψη."

    db.commit()

    return RedirectResponse(
        url=f"/projects/{product.project_id}",
        status_code=302
    )
