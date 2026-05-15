from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(String(50), default="admin")

    created_at = Column(DateTime, default=datetime.utcnow)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)

    project_token = Column(String(100), unique=True, index=True, nullable=False)

    store_name = Column(String(255), nullable=False)
    store_email = Column(String(255), nullable=True)
    salesforce_grid = Column(String(255), nullable=True)

    original_filename = Column(String(255), nullable=True)

    drive_folder_id = Column(String(255), nullable=True)
    drive_folder_url = Column(Text, nullable=True)

    status = Column(String(50), default="active")

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="project")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    barcode = Column(String(255), nullable=True)
    item_name = Column(Text, nullable=False)
    sku = Column(String(255), nullable=True)
    product_id = Column(String(255), nullable=True)
    category = Column(String(255), nullable=True)

    photo_status = Column(String(50), default="missing")

    photo_filename = Column(String(255), nullable=True)
    photo_drive_file_id = Column(String(255), nullable=True)
    photo_drive_url = Column(Text, nullable=True)

    reject_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="products")
