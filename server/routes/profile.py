"""User profile routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..logging_config import logger
from ..services.user_profile import get_user_profile

router = APIRouter(prefix="/profile", tags=["profile"])


class UserProfileData(BaseModel):
    """User profile data."""
    userName: str = ""
    birthDate: str = ""
    location: str = ""


@router.post("/save")
def save_profile(profile: UserProfileData):
    """Save user profile."""
    try:
        profile_store = get_user_profile()
        profile_dict = {
            "userName": profile.userName,
            "birthDate": profile.birthDate,
            "location": profile.location,
        }

        logger.info(f"💾 Saving user profile: userName='{profile.userName}', birthDate='{profile.birthDate}', location='{profile.location}'")

        profile_store.save(profile_dict)

        # Verify it was saved
        loaded = profile_store.load()
        logger.info(f"✅ Profile saved and verified: {loaded}")

        return {"ok": True, "saved": profile_dict, "verified": loaded}

    except Exception as exc:
        logger.error(f"❌ Failed to save profile: error={exc}, profile={profile.dict()}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/load")
def load_profile():
    """Load user profile."""
    try:
        profile_store = get_user_profile()
        profile_data = profile_store.load()

        logger.info(f"📖 Loading user profile: {profile_data}")

        return {
            "ok": True,
            "profile": {
                "userName": profile_data.get("userName", ""),
                "birthDate": profile_data.get("birthDate", ""),
                "location": profile_data.get("location", ""),
            }
        }

    except Exception as exc:
        logger.error(f"❌ Failed to load profile: error={exc}")
        raise HTTPException(status_code=500, detail=str(exc))
