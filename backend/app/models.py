from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="farmer", index=True)
    preferred_language: Mapped[str] = mapped_column(String(20), default="ta")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    farmer_profile = relationship("FarmerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    officer_profile = relationship("OfficerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    disease_reports = relationship("DiseaseReport", back_populates="user", cascade="all, delete-orphan")


class FarmerProfile(Base, TimestampMixin):
    __tablename__ = "farmer_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    village: Mapped[str | None] = mapped_column(String(100), nullable=True)
    land_size_acres: Mapped[float | None] = mapped_column(Float, nullable=True)
    primary_crop: Mapped[str | None] = mapped_column(String(100), nullable=True)
    irrigation_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    farmer_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    annual_income: Mapped[float | None] = mapped_column(Float, nullable=True)

    user = relationship("User", back_populates="farmer_profile")


class OfficerProfile(Base, TimestampMixin):
    __tablename__ = "officer_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    department: Mapped[str | None] = mapped_column(String(150), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(150), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)

    user = relationship("User", back_populates="officer_profile")
    assigned_grievances = relationship("Grievance", back_populates="assigned_officer")


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(20), default="ta")

    user = relationship("User", back_populates="conversations")


class Grievance(Base, TimestampMixin):
    __tablename__ = "grievances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tracking_id: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_officer_id: Mapped[int | None] = mapped_column(ForeignKey("officer_profiles.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="submitted", index=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_resolution_days: Mapped[int] = mapped_column(Integer, default=30)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    farmer = relationship("User")
    assigned_officer = relationship("OfficerProfile", back_populates="assigned_grievances")
    updates = relationship("GrievanceUpdate", back_populates="grievance", cascade="all, delete-orphan")


class GrievanceUpdate(Base, TimestampMixin):
    __tablename__ = "grievance_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    grievance_id: Mapped[int] = mapped_column(ForeignKey("grievances.id"), nullable=False)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    old_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    grievance = relationship("Grievance", back_populates="updates")
    updater = relationship("User")


class DiseaseReport(Base, TimestampMixin):
    __tablename__ = "disease_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    crop_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    disease_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    pest_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    treatment: Mapped[str | None] = mapped_column(Text, nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(60), default="completed", index=True)
    analysis_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user = relationship("User", back_populates="disease_reports")


class Scheme(Base, TimestampMixin):
    __tablename__ = "schemes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    eligibility_criteria: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    benefits: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_documents: Mapped[list | None] = mapped_column(JSON, nullable=True)
    application_process: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SchemeCheck(Base, TimestampMixin):
    __tablename__ = "scheme_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    scheme_name: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    land_ownership: Mapped[str | None] = mapped_column(String(100), nullable=True)
    farmer_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    annual_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_eligible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    eligibility_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    alternative_schemes: Mapped[list | None] = mapped_column(JSON, nullable=True)

    user = relationship("User")


class AnalyticsEvent(Base, TimestampMixin):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)

    user = relationship("User")


class IvrSession(Base, TimestampMixin):
    __tablename__ = "ivr_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    phone_number: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="mock")
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    current_state: Mapped[str] = mapped_column(String(80), default="LANGUAGE_SELECTION", index=True)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    last_intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
