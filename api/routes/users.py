# library imports
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
# module imports
from core.oauth2 import get_current_user
from core.db import db
from models.user import User,UserResponse
from core.utils import get_password_hash
from core.send_email import send_registration_mail
from datetime import datetime, timedelta

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


@router.post("/registration", response_description="Register New User", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def registration(user_info: User):
    user_info = jsonable_encoder(user_info)

    # check for duplications
    username_found = await db["users"].find_one({"name": user_info["name"]})
    email_found = await db["users"].find_one({"email": user_info["email"]})

    if username_found:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="There already is a user by that name")

    if email_found:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="There already is a user by that email")

    # hash the user password
    user_info["password"] = get_password_hash(user_info["password"])

    # generate apiKey
    # user_info["apiKey"] = secrets.token_hex(20)

    #add registered time and date
    user_info["trial_start_date"] = datetime.now()
    user_info["trial_end_date"] = datetime.now() + timedelta(days=7)

    new_user = await db["users"].insert_one(user_info)
    created_user = await db["users"].find_one({"_id": new_user.inserted_id})

    # send email
    await send_registration_mail("Registration successful", user_info["email"],
        {
            "title": "Registration successful",
            "name": user_info["name"],
            "role": user_info["role"]

        }
    )

    return created_user


@router.post("/details", response_description="Get user details", response_model=UserResponse)
async def details(current_user=Depends(get_current_user)):
    user = await db["users"].find_one({"_id": current_user["_id"]})
    return user