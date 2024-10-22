# Library imports
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from api.models.user import PasswordReset, PasswordResetRequest
from api.core.db import db
from api.core.send_email import password_reset
from api.core.oauth2 import create_access_token, get_current_user
from api.core.utils import get_password_hash

router = APIRouter(
    prefix="/password",
    tags=["Password Reset"]
)

@router.post("/request/", response_description="Password reset request")
async def reset_request(user_email: PasswordResetRequest):
    # Find user by email
    user = await db["users"].find_one({"email": user_email.email})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Your details not found, invalid email address"
        )

    # Create a reset token
    token = create_access_token({"id": str(user["_id"])})
    # reset_link = f"http://localhost:8000/reset?token={token}"
    reset_link = f"http://alvision-reset-password.s3-website.ap-south-1.amazonaws.com/reset?token={token}"
      # Corrected 'localhost' spelling

    # Send password reset email
    await password_reset("Password Reset", user["email"],
        {
            "title": "Password Reset",
            "name": user["name"],
            "reset_link": reset_link
        }
    )
    return {"msg": "Email has been sent with instructions to reset your password."}


@router.put("/reset/", response_description="Password reset")
async def reset_password(token: str, new_password: PasswordReset):
    # Verify the token and retrieve the user
    user = await get_current_user(token)

    print("i am here")
    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    # Hash the new password
    hashed_password = get_password_hash(new_password.password)

    # Update the password in the database
    update_result = await db["users"].update_one(
        {"_id": user["_id"]}, {"$set": {"password": hashed_password}}
    )

    # Check if the password was successfully updated
    if update_result.modified_count != 1:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update the password"
        )

    return {"msg": "Password successfully reset"}