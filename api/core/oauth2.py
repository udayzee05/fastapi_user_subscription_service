# library imports
from typing import Dict,Optional
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi import Depends, status, HTTPException
from fastapi.security import OAuth2PasswordBearer
from api.config import settings
from jose.exceptions import ExpiredSignatureError
import logging

# module imports
from api.core.db import db
from api.models.user import TokenData

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# get config values
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES


# Helper to check if token is blacklisted
async def is_token_blacklisted(token: str) -> bool:
    blacklisted_token = await db["blacklist_token"].find_one({"token": token})
    return blacklisted_token is not None


def create_access_token(data: Dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

# 2. Verify Access Token with Blacklist Check
async def verify_access_token(token: str) -> TokenData:
    # Check if the token is blacklisted
    if await is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been invalidated. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"}
            )
        return TokenData(id=user_id)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except JWTError as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )

async def get_current_user(token: str = Depends(oauth2_scheme)):
    token_data = await verify_access_token(token)
    user = await db["users"].find_one({"_id": token_data.id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user
