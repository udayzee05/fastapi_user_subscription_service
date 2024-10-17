
import logging
from fastapi import Depends, HTTPException,UploadFile,File
from api.core.db import db
from api.models.user import User
from api.core.oauth2 import get_current_user
from PIL import Image
import uuid
import os
from api.core.aws import AWSConfig
from fastapi import APIRouter
from api.models.user import UserProfileUpdate,UserProfileResponse


router = APIRouter(prefix="/userProfile", tags=["User Profile"])

# Logging configuration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

aws_config = AWSConfig()

users_collection = db['users']  # Assuming you have a 'users' collection

@router.put("profile_update", response_model=UserProfileResponse)
async def update_profile(
    profile_update: UserProfileUpdate,
    current_user: dict = Depends(get_current_user),  # Assuming current_user comes from DB and is a dict
):
    """
    Update the profile information of the currently logged-in user.
    """
    # Debug current_user and check its content

    if "_id" not in current_user:
        raise HTTPException(status_code=400, detail="User ID not found in the current user")

    user_id = current_user["_id"]
    print(user_id)

    # Convert the Pydantic model `UserProfileUpdate` to a dictionary, excluding unset fields
    update_data = profile_update.model_dump(exclude_unset=True)

    # Perform the asynchronous MongoDB update using Motor
    result = await users_collection.update_one(
        {"_id": user_id},
        {"$set": update_data}
    )

    # Check if the update was successful
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch updated user info from the DB and return it
    updated_user = await users_collection.find_one({"_id": user_id})
    
    if not updated_user:
        raise HTTPException(status_code=404, detail="Updated user not found")

    return UserProfileResponse(
        role=updated_user.get("role"),
        email=updated_user.get("email"),
        company_email=updated_user.get("company_email"),
        phone_number=updated_user.get("phone_number"),
        gstin_number=updated_user.get("gstin_number"),
        profile_picture=updated_user.get("profile_picture")
    )



@router.get("profile", response_model=UserProfileResponse)
async def get_profile(current_user: User = Depends(get_current_user)):
    """
    Get the profile of the currently logged-in user with specific details.
    """
    current_user = User(**current_user)
    return UserProfileResponse(
        email=current_user.email,
        role=current_user.role,
        company_email=current_user.company_email,
        phone_number=current_user.phone_number,
        gstin_number=current_user.gstin_number,
        profile_picture=current_user.profile_picture,
    )


@router.put("profile_picture")
async def update_profile_picture(
    profile_picture: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)  # Assuming `get_current_user` returns a dict
):
    """
    Update the profile picture of the currently logged-in user.
    """
    # Debug current_user and check its content

    if "_id" not in current_user:
        raise HTTPException(status_code=400, detail="User ID not found in the current user")

    user_id = current_user["_id"]

    # Ensure the file is an image
    if not profile_picture.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # Save the uploaded file locally
    processed_image_path = f"../static/raw_{uuid.uuid4()}.png"
    with open(processed_image_path, "wb+") as file_object:
        file_object.write(profile_picture.file.read())

    # Process the image (if needed)
    profile_pic_path = f"../static/profile_pic_{uuid.uuid4()}.png"
    with Image.open(processed_image_path) as img:
        profile_pic = img.convert("RGB")  # Example processing step
        profile_pic.save(profile_pic_path)

    # Upload the processed image to S3 under the 'profile_pic' directory
    bucket_name = "countwebapp"  # Replace with your bucket name
    object_name = f"profile_pic/{uuid.uuid4()}.png"
    profile_pic_url = aws_config.upload_to_s3(profile_pic_path, bucket_name, object_name)

    if profile_pic_url is None:
        raise HTTPException(status_code=500, detail="Failed to upload the profile picture to S3")

    # Update the user's profile with the S3 URL using Motor
    result = await users_collection.update_one(
        {"_id": user_id},
        {"$set": {"profile_picture": profile_pic_url}}
    )

    # Check if the update was successful
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch updated user info from the DB
    updated_user = await users_collection.find_one({"_id": user_id})
    
    if not updated_user:
        raise HTTPException(status_code=404, detail="Updated user not found")

    # Clean up local files (optional)
    os.remove(processed_image_path)
    os.remove(profile_pic_path)

    return {
        "msg": "Profile picture updated successfully",
        "profile_picture_url": profile_pic_url
    }




