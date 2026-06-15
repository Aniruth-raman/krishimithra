from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.models import User
from app.services.weather_service import WeatherLookupError, fetch_weather


router = APIRouter(prefix="/weather", tags=["Weather"])


@router.get("/current")
async def current_weather(
    location: str = Query(..., min_length=2, max_length=120),
    current_user: User = Depends(get_current_user),
):
    try:
        return await fetch_weather(location)
    except WeatherLookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail="Weather provider is unavailable. Please try again shortly.") from error


@router.get("/me")
async def my_weather(current_user: User = Depends(get_current_user)):
    profile = current_user.farmer_profile
    location = None
    if profile:
        location = profile.district or profile.village or profile.state
    if not location:
        raise HTTPException(status_code=400, detail="Add district or village in your farmer profile to use weather.")
    try:
        return await fetch_weather(location)
    except WeatherLookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail="Weather provider is unavailable. Please try again shortly.") from error
