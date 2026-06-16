from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import User, SchemeCheck, Scheme, AnalyticsEvent
from app.schemas import SchemeCheckRequest, SchemeCheckOut, SchemeCreate, SchemeOut
from app.auth import get_current_user, get_admin
from app.services.ai.sarvam_ai_service import check_scheme_eligibility

router = APIRouter(prefix="/scheme", tags=["Scheme Eligibility"])

AVAILABLE_SCHEMES = [
    "PM-KISAN",
    "Raitha Sakthi Yojana",
    "Krushak Yojana",
    "Mukhyamantri Samathuvapuram",
    "PM Fasal Bima Yojana",
    "Kisan Credit Card",
    "National Agriculture Market (eNAM)",
    "Pradhan Mantri Krishi Sinchayee Yojana",
    "Soil Health Card Scheme"
]


@router.get("/list")
async def list_schemes(db: Session = Depends(get_db)):
    """Get all available schemes."""
    db_schemes = db.query(Scheme).filter(Scheme.is_active == True).all()
    if db_schemes:
        return db_schemes
    # Return default list if none in DB
    return [{"name": s, "description": f"Government agricultural scheme: {s}"} for s in AVAILABLE_SCHEMES]


@router.post("/check")
async def check_eligibility(
    request: SchemeCheckRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check farmer's eligibility for a specific scheme."""
    language = current_user.preferred_language or "ta"
    
    result = await check_scheme_eligibility(
        scheme_name=request.scheme_name,
        state=request.state,
        land_ownership=request.land_ownership,
        farmer_category=request.farmer_category,
        annual_income=request.annual_income,
        language=language
    )

    # Store check result
    check = SchemeCheck(
        user_id=current_user.id,
        scheme_name=request.scheme_name,
        state=request.state,
        land_ownership=request.land_ownership,
        farmer_category=request.farmer_category,
        annual_income=request.annual_income,
        is_eligible=result.get("is_eligible"),
        eligibility_reason=result.get("eligibility_reason"),
        alternative_schemes=result.get("alternative_schemes", [])
    )
    db.add(check)

    # Log analytics
    db.add(AnalyticsEvent(
        event_type="scheme_check",
        user_id=current_user.id,
        data={"scheme": request.scheme_name, "eligible": result.get("is_eligible")}
    ))
    db.commit()
    db.refresh(check)

    return {
        "id": check.id,
        "scheme_name": check.scheme_name,
        "is_eligible": result.get("is_eligible"),
        "eligibility_status": result.get("eligibility_status", "eligible" if result.get("is_eligible") is True else "not_eligible" if result.get("is_eligible") is False else "requires_verification"),
        "eligibility_reason": result.get("eligibility_reason"),
        "benefits": result.get("benefits"),
        "required_documents": result.get("required_documents", []),
        "alternative_schemes": result.get("alternative_schemes", []),
        "application_steps": result.get("application_steps"),
        "created_at": check.created_at
    }


@router.get("/history")
async def get_scheme_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    checks = (
        db.query(SchemeCheck)
        .filter(SchemeCheck.user_id == current_user.id)
        .order_by(SchemeCheck.created_at.desc())
        .limit(20)
        .all()
    )
    return checks


# Admin endpoints
@router.post("/admin/create", response_model=SchemeOut)
async def create_scheme(
    data: SchemeCreate,
    current_user: User = Depends(get_admin),
    db: Session = Depends(get_db)
):
    scheme = Scheme(**data.model_dump())
    db.add(scheme)
    db.commit()
    db.refresh(scheme)
    return scheme


@router.get("/admin/all", response_model=List[SchemeOut])
async def get_all_schemes(
    current_user: User = Depends(get_admin),
    db: Session = Depends(get_db)
):
    return db.query(Scheme).all()
