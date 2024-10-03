# library imports
# pip install "passlib[bcrypt]"
from passlib.context import CryptContext
from fastapi import Depends, HTTPException

from schemas import User
from core.oauth2 import get_current_user


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)



async def check_admin_user(user: dict = Depends(get_current_user)):
    if not isinstance(user, User):
        user = User(**user)
    if user.role != "admin":
        raise HTTPException(
            status_code=403, detail="Access forbidden: Requires admin role"
        )
    return user



