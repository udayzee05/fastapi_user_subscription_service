# library imports
from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

# module imports
from schemas import db, Token
from core.oauth2 import create_access_token
from core.utils import verify_password

router = APIRouter(
    prefix="/login",
    tags=["Authentication"]
)

@router.post("", response_model=Token, status_code=status.HTTP_200_OK)
async def login(user_credentials: OAuth2PasswordRequestForm = Depends()):

    user = await db["users"].find_one({
        "$or": [
            {"name": user_credentials.username},
            {"email": user_credentials.username}
        ]
    })

    if user and verify_password(user_credentials.password, user["password"]):
        access_token = create_access_token(payload={
            "id": user["_id"],
        })
        return {"access_token": access_token, "token_type": "bearer"}
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid user credentials"
        )
