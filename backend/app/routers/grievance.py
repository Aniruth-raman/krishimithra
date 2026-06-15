import uuid
import random
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models import User, Grievance, GrievanceUpdate, OfficerProfile, AnalyticsEvent
from app.schemas import GrievanceCreate, GrievanceOut, GrievanceStatusUpdate
from app.auth import get_current_user, get_officer
from app.services.ai.sarvam_ai_service import classify_grievance

router = APIRouter(prefix="/grievance", tags=["Grievance"])

RESOLUTION_DAYS = {
    "Subsidy Delay": 15,
    "Crop Loss": 30,
    "Insurance": 45,
    "Irrigation": 20,
    "Market Rate Issue": 10
}


def generate_tracking_id() -> str:
    year = datetime.now().year
    random_part = random.randint(10000, 99999)
    return f"GRV{year}{random_part}"


def enum_value(value) -> Optional[str]:
    if value is None:
        return None
    return str(value.value) if hasattr(value, "value") else str(value)


def serialize_officer_grievance(grievance: Grievance, include_updates: bool = False) -> dict:
    due_at = grievance.created_at + timedelta(days=grievance.expected_resolution_days)
    days_remaining = (due_at.date() - datetime.utcnow().date()).days
    closed = grievance.status in {"resolved", "closed"}
    sla_status = "closed" if closed else "breached" if days_remaining < 0 else "due_soon" if days_remaining <= 2 else "on_track"
    assigned_officer = None
    if grievance.assigned_officer and grievance.assigned_officer.user:
        assigned_officer = grievance.assigned_officer.user.full_name

    data = {
        "id": grievance.id,
        "tracking_id": grievance.tracking_id,
        "category": enum_value(grievance.category),
        "title": grievance.title,
        "description": grievance.description,
        "status": enum_value(grievance.status),
        "district": grievance.district,
        "farmer_name": grievance.farmer.full_name if grievance.farmer else None,
        "farmer_phone": grievance.farmer.phone if grievance.farmer else None,
        "assigned_officer": assigned_officer,
        "assigned_officer_id": grievance.assigned_officer_id,
        "expected_resolution_days": grievance.expected_resolution_days,
        "due_at": due_at,
        "days_remaining": days_remaining,
        "sla_status": sla_status,
        "resolution_notes": grievance.resolution_notes,
        "created_at": grievance.created_at,
        "updated_at": grievance.updated_at,
        "resolved_at": grievance.resolved_at,
    }

    if include_updates:
        data["updates"] = [
            {
                "id": update.id,
                "old_status": update.old_status,
                "status": update.new_status,
                "notes": update.notes,
                "updated_by": update.updater.full_name if update.updater else None,
                "created_at": update.created_at,
            }
            for update in sorted(grievance.updates, key=lambda item: item.created_at, reverse=True)
        ]

    return data


@router.post("/create", response_model=GrievanceOut)
async def create_grievance(
    data: GrievanceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Auto-classify if no category or refine description
    tracking_id = generate_tracking_id()

    # Ensure unique tracking ID
    while db.query(Grievance).filter(Grievance.tracking_id == tracking_id).first():
        tracking_id = generate_tracking_id()

    # Get district from farmer profile
    district = data.district
    if not district and current_user.farmer_profile:
        district = current_user.farmer_profile.district

    grievance = Grievance(
        tracking_id=tracking_id,
        farmer_id=current_user.id,
        category=data.category,
        title=data.title,
        description=data.description,
        district=district,
        expected_resolution_days=RESOLUTION_DAYS.get(enum_value(data.category), 30)
    )
    db.add(grievance)

    # Log analytics
    db.add(AnalyticsEvent(
        event_type="grievance_created",
        user_id=current_user.id,
        data={"category": str(data.category), "tracking_id": tracking_id},
        district=district
    ))
    db.commit()
    db.refresh(grievance)

    return grievance


@router.get("/track/{tracking_id}")
async def track_grievance(
    tracking_id: str,
    db: Session = Depends(get_db)
):
    """Public endpoint - track grievance by ID."""
    grievance = db.query(Grievance).filter(Grievance.tracking_id == tracking_id).first()
    if not grievance:
        raise HTTPException(status_code=404, detail=f"Grievance {tracking_id} not found")

    updates = db.query(GrievanceUpdate).filter(
        GrievanceUpdate.grievance_id == grievance.id
    ).order_by(GrievanceUpdate.created_at.desc()).all()

    officer_name = None
    if grievance.assigned_officer:
        officer_name = grievance.assigned_officer.user.full_name if grievance.assigned_officer.user else None

    return {
        "tracking_id": grievance.tracking_id,
        "category": enum_value(grievance.category),
        "title": grievance.title,
        "description": grievance.description,
        "status": enum_value(grievance.status),
        "district": grievance.district,
        "assigned_officer": officer_name,
        "expected_resolution_days": grievance.expected_resolution_days,
        "resolution_notes": grievance.resolution_notes,
        "created_at": grievance.created_at,
        "updated_at": grievance.updated_at,
        "updates": [
            {
                "status": u.new_status,
                "notes": u.notes,
                "date": u.created_at
            } for u in updates
        ]
    }


@router.get("/my")
async def get_my_grievances(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Grievance).filter(Grievance.farmer_id == current_user.id)
    if status:
        query = query.filter(Grievance.status == status)
    grievances = query.order_by(Grievance.created_at.desc()).all()
    return [
        {
            "id": g.id,
            "tracking_id": g.tracking_id,
            "category": enum_value(g.category),
            "title": g.title,
            "status": enum_value(g.status),
            "district": g.district,
            "created_at": g.created_at
        }
        for g in grievances
    ]


# Officer endpoints
@router.get("/officer/all")
async def get_all_grievances(
    status: Optional[str] = None,
    category: Optional[str] = None,
    district: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_officer),
    db: Session = Depends(get_db)
):
    query = db.query(Grievance)
    if status:
        query = query.filter(Grievance.status == status)
    if category:
        query = query.filter(Grievance.category == category)
    if district:
        query = query.filter(Grievance.district == district)

    total = query.count()
    grievances = query.order_by(Grievance.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "data": [serialize_officer_grievance(g) for g in grievances]
    }


@router.get("/officer/staff")
async def get_officer_staff(
    current_user: User = Depends(get_officer),
    db: Session = Depends(get_db)
):
    officers = db.query(OfficerProfile).join(User).filter(User.is_active == True).all()
    return [
        {
            "id": officer.id,
            "name": officer.user.full_name if officer.user else "Officer",
            "district": officer.district,
            "designation": officer.designation,
            "department": officer.department,
        }
        for officer in officers
    ]


@router.get("/officer/track/{tracking_id}")
async def get_officer_grievance_by_tracking_id(
    tracking_id: str,
    current_user: User = Depends(get_officer),
    db: Session = Depends(get_db)
):
    grievance = db.query(Grievance).filter(Grievance.tracking_id == tracking_id).first()
    if not grievance:
        raise HTTPException(status_code=404, detail=f"Grievance {tracking_id} not found")
    return serialize_officer_grievance(grievance, include_updates=True)


@router.get("/officer/{grievance_id}")
async def get_officer_grievance(
    grievance_id: int,
    current_user: User = Depends(get_officer),
    db: Session = Depends(get_db)
):
    grievance = db.query(Grievance).filter(Grievance.id == grievance_id).first()
    if not grievance:
        raise HTTPException(status_code=404, detail="Grievance not found")
    return serialize_officer_grievance(grievance, include_updates=True)


@router.put("/officer/{grievance_id}")
async def update_grievance_status(
    grievance_id: int,
    data: GrievanceStatusUpdate,
    current_user: User = Depends(get_officer),
    db: Session = Depends(get_db)
):
    grievance = db.query(Grievance).filter(Grievance.id == grievance_id).first()
    if not grievance:
        raise HTTPException(status_code=404, detail="Grievance not found")

    old_status = grievance.status

    if data.assigned_officer_id:
        officer = db.query(OfficerProfile).filter(OfficerProfile.id == data.assigned_officer_id).first()
        if not officer:
            raise HTTPException(status_code=404, detail="Officer not found")
        grievance.assigned_officer_id = officer.id
    elif not grievance.assigned_officer_id and current_user.officer_profile:
        grievance.assigned_officer_id = current_user.officer_profile.id

    grievance.status = data.status
    if data.status in {"resolved", "closed"}:
        grievance.resolved_at = datetime.utcnow()
        grievance.resolution_notes = data.notes

    # Create update record
    update = GrievanceUpdate(
        grievance_id=grievance.id,
        updated_by=current_user.id,
        old_status=enum_value(old_status),
        new_status=enum_value(data.status),
        notes=data.notes
    )
    db.add(update)
    db.commit()
    db.refresh(grievance)

    return {"message": "Grievance updated successfully", "tracking_id": grievance.tracking_id, "new_status": data.status}
