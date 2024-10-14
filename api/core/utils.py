# library imports
# pip install "passlib[bcrypt]"
import logging
import base64
import os
import uuid
from core.aws import AWSConfig
from datetime import datetime
import logging
from passlib.context import CryptContext
from fastapi import Depends, HTTPException,status

from core.db import db
from models.user import User
from core.oauth2 import get_current_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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



# Dependency to check if the user has a valid subscription
async def check_valid_subscription(current_user: User = Depends(get_current_user)):
    """
    Dependency function to check if the user has an active or completed subscription.
    """
    try:
        # Fetch user's subscriptions from the database
        user_subscriptions = await db.subscriptions.find({"user_id": current_user["_id"]}).to_list(length=None)
        
        # Check if any subscription is active or completed
        valid_subscription = any(sub['status'] in ["active"] for sub in user_subscriptions)
        
        if not valid_subscription:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: No active or completed subscription found."
            )
        
        return True  # Return True if the user has a valid subscription
    
    except Exception as e:
        logger.error(f"Error while checking subscription: {str(e)}")
        raise HTTPException(status_code=500, detail="Error checking subscription status")
    

def valid_subscription_for_service(service_base_name: str):
    """
    Check if the user has an active subscription for a given service (regardless of its duration).
    This function will check for 'service_base_name' (e.g., 'TelescopicPipe') with different subscription durations.
    """
    async def check(user: User = Depends(get_current_user)):
        try:
            # Fetch the user's subscribed services from the database
            user_data = await db.users.find_one({"_id": user["_id"]})
            subscribed_services = user_data.get("subscribed_services", [])

            # Define the possible subscription types for the service (monthly, quarterly, yearly)
            possible_subscriptions = [
                f"{service_base_name} monthly",
                f"{service_base_name} quarterly",
                f"{service_base_name} half-yearly",
                f"{service_base_name} yearly"
            ]

            print(possible_subscriptions)

            # Check if the user has any active subscription for the service (regardless of duration)
            valid_subscription = any(service in subscribed_services for service in possible_subscriptions)

            if not valid_subscription:
                logging.error(f"Access denied: No active subscription found for {service_base_name}.")
                return False  # No active subscription found
            return True  # Valid subscription found

        except Exception as e:
            logging.error(f"Error while checking subscription for {service_base_name}: {str(e)}")
            raise HTTPException(status_code=500, detail="Error checking subscription status")
    
    return check






# Assuming you have these imported already
# from your_aws_module import AWSConfig

logger = logging.getLogger(__name__)

async def save_base64_image(base64_str,SERVICE_NAME):
    try:
        # Decode the base64 string to binary data
        image_data = base64.b64decode(base64_str)
    except base64.binascii.Error:
        logger.error("Invalid base64 format")
        raise ValueError(
            "Invalid base64 format. Please submit a valid base64-encoded image."
        )

    # Get the current date for organizing by year and month
    current_date = datetime.now()
    year = current_date.strftime("%Y")
    month = current_date.strftime("%m")

    # Define the local path for saving the image, organized by year/month
    local_image_dir = f"../static/{year}/{month}"
    os.makedirs(local_image_dir, exist_ok=True)  # Ensure the directory exists

    # Define the image path
    original_image_filename = f"original_{uuid.uuid4()}.png"
    original_image_path = os.path.join(local_image_dir, original_image_filename)

    # Write the image data to a local file
    with open(original_image_path, "wb") as f:
        f.write(image_data)

    # Define the bucket and object path in S3, organized by year/month
    bucket_name = "alvision-count"
    object_name = f"count/{SERVICE_NAME}/original/{year}/{month}/{original_image_filename}"

    # Use the existing upload_to_s3 method
    aws_config = AWSConfig()
    original_image_url = aws_config.upload_to_s3(
        original_image_path, bucket_name, object_name
    )

    logger.info(f"Original image saved to {original_image_url}")

    # Optionally, remove the local file if not needed
    os.remove(original_image_path)

    return original_image_url
