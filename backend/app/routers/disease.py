import os
import uuid
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import AnalyticsEvent, DiseaseReport, User
from app.services.ai.sarvam_ai_service import analyze_crop_image


router = APIRouter(prefix="/disease", tags=["Disease Detection"])

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_SIZE = 10 * 1024 * 1024
MIN_IMAGE_DIMENSION = 64
MAX_IMAGE_PIXELS = 25_000_000

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def validate_crop_image(image: UploadFile, content: bytes) -> dict:
    filename = image.filename or ""
    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file extension. Upload JPG, JPEG, PNG, or WebP.")

    if image.content_type and image.content_type.lower() not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Invalid image type. Upload JPG, JPEG, PNG, or WebP.")

    if not content:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Max 10MB allowed.")

    try:
        with Image.open(BytesIO(content)) as image_file:
            image_file.verify()
        with Image.open(BytesIO(content)) as image_file:
            image_format = image_file.format
            width, height = image_file.size
    except Image.DecompressionBombError as error:
        raise HTTPException(status_code=400, detail="Image is too large to process safely.") from error
    except (UnidentifiedImageError, OSError) as error:
        raise HTTPException(status_code=400, detail="Invalid or corrupted image file.") from error

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise HTTPException(status_code=400, detail="Unsupported image format. Upload JPG, JPEG, PNG, or WebP.")
    if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
        raise HTTPException(status_code=400, detail="Image is too small for crop disease analysis.")

    return {"format": image_format, "width": width, "height": height, "extension": extension}


@router.post("/analyze")
async def analyze_disease(
    image: UploadFile = File(...),
    crop_type: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = await image.read()
    metadata = validate_crop_image(image, content)

    filename = f"{uuid.uuid4()}{metadata['extension']}"
    image_path = os.path.join(settings.UPLOAD_DIR, filename)
    with open(image_path, "wb") as image_file:
        image_file.write(content)

    analysis = await analyze_crop_image(image_path, crop_type)

    district = None
    if current_user.farmer_profile:
        district = current_user.farmer_profile.district

    report = DiseaseReport(
        user_id=current_user.id,
        crop_type=crop_type,
        image_path=image_path,
        disease_name=analysis.get("disease_name"),
        pest_name=analysis.get("pest_name"),
        severity=analysis.get("severity"),
        confidence_score=analysis.get("confidence_score"),
        description=analysis.get("description"),
        treatment=analysis.get("treatment"),
        district=district,
        analysis_json={"image": metadata, "analysis": analysis},
    )
    db.add(report)

    db.add(
        AnalyticsEvent(
            event_type="disease_report",
            user_id=current_user.id,
            data={"disease": analysis.get("disease_name"), "crop": crop_type, "severity": analysis.get("severity")},
            district=district,
        )
    )
    db.commit()
    db.refresh(report)

    return {
        "id": report.id,
        "crop_type": report.crop_type,
        "disease_name": report.disease_name,
        "pest_name": report.pest_name,
        "severity": report.severity,
        "confidence_score": report.confidence_score,
        "description": report.description,
        "treatment": report.treatment,
        "preventive_measures": analysis.get("preventive_measures"),
        "image_url": f"/uploads/{filename}",
        "image_validation": metadata,
        "created_at": report.created_at,
    }


@router.get("/hotspots")
async def disease_hotspots(
    days: int = 30,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    days = max(1, min(days, 365))
    limit = max(1, min(limit, 50))
    since = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(
            DiseaseReport.district,
            DiseaseReport.disease_name,
            DiseaseReport.pest_name,
            DiseaseReport.severity,
            func.count(DiseaseReport.id).label("case_count"),
            func.max(DiseaseReport.created_at).label("latest_reported_at"),
        )
        .filter(DiseaseReport.created_at >= since)
        .filter(DiseaseReport.district.isnot(None))
        .group_by(DiseaseReport.district, DiseaseReport.disease_name, DiseaseReport.pest_name, DiseaseReport.severity)
        .order_by(func.count(DiseaseReport.id).desc(), func.max(DiseaseReport.created_at).desc())
        .limit(limit)
        .all()
    )

    severity_score = {"low": 1, "medium": 2, "moderate": 2, "high": 3, "severe": 4, "critical": 4}
    hotspots = []
    for row in rows:
        severity = (row.severity or "unknown").lower()
        case_count = int(row.case_count or 0)
        hotspots.append(
            {
                "district": row.district,
                "issue": row.disease_name or row.pest_name or "Unclassified crop issue",
                "severity": row.severity or "unknown",
                "case_count": case_count,
                "risk_score": case_count * severity_score.get(severity, 1),
                "latest_reported_at": row.latest_reported_at,
            }
        )

    return {"days": days, "hotspots": sorted(hotspots, key=lambda item: item["risk_score"], reverse=True)}


@router.get("/reports")
async def get_my_reports(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reports = (
        db.query(DiseaseReport)
        .filter(DiseaseReport.user_id == current_user.id)
        .order_by(DiseaseReport.created_at.desc())
        .limit(limit)
        .all()
    )
    return reports


@router.get("/reports/{report_id}")
async def get_report(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(DiseaseReport).filter(DiseaseReport.id == report_id, DiseaseReport.user_id == current_user.id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report
