from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from api.models.user import Token
from api.core.db import db
from api.core.oauth2 import create_access_token
from api.core.utils import verify_password
import logging

router = APIRouter(
    prefix="/login",
    tags=["Authentication"]
)


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@router.post("", response_model=Token, status_code=status.HTTP_200_OK)
async def login(user_credentials: OAuth2PasswordRequestForm = Depends()):
    # Fetch the user from the database based on username or email
    user = await db["users"].find_one({
        "$or": [
            {"name": user_credentials.username},
            {"email": user_credentials.username}
        ]
    })

    if not user:
        logger.warning("User not found: %s", user_credentials.username)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Verify the password
    if not verify_password(user_credentials.password, user["password"]):
        logger.warning("Invalid credentials for user: %s", user_credentials.username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid user credentials"
        )

    # Create access token
    access_token = create_access_token(payload={"id": str(user["_id"])})

    # Extract subscribed services
    subscribed_services = user.get("subscribed_services", [])

    logger.info("User %s logged in successfully", user_credentials.username)

    # Return the access token and subscribed services
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "subscribed_services": subscribed_services
    }
