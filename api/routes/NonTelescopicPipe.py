
import logging

from fastapi import Depends, Request, HTTPException

from schemas import User, db,ObjectCount,ObjectCountResponse,CountRequest
from core.oauth2 import get_current_user
from core.utils import check_valid_subscription
from PIL import Image
import cv2
import base64
import uuid
from datetime import datetime,timedelta
import os
from api.services.NonTelescopicPipe import count_objects_with_yolo, get_segmented_pipes
from api.core.aws import AWSConfig
from fastapi import APIRouter



router = APIRouter(prefix="/NonTelescopicPipe", tags=["NonTelescopicPipe"])

# Logging configuration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


aws_config = AWSConfig()

async def save_base64_image(base64_str):
    try:
        image_data = base64.b64decode(base64_str)
    except base64.binascii.Error:
        logger.error("Invalid base64 format")
        raise ValueError(
            "Invalid base64 format. Please submit a valid base64-encoded image."
        )

    # Define the local path for saving the image
    original_image_path = f"../static/original_{uuid.uuid4()}.png"

    # Write the image data to a local file
    with open(original_image_path, "wb") as f:
        f.write(image_data)

    bucket_name = "alvision-count"
    object_name = f"count/original/original_{uuid.uuid4()}.png"

    # Use the existing upload_to_s3 method
    aws_config = AWSConfig()
    original_image_url = aws_config.upload_to_s3(
        original_image_path, bucket_name, object_name
    )

    logger.info(f"Original image saved to {original_image_url}")

    # Optionally, remove the local file if not needed
    os.remove(original_image_path)

    return original_image_url


# async def get_current_admin_user(user: dict = Depends(get_current_user)):
#     if not isinstance(user, User):
#         user = User(**user)
#     if user.role != "admin":
#         raise HTTPException(
#             status_code=403, detail="Access forbidden: Requires admin role"
#         )
#     return user

@router.post("/nonTelescopic")
async def count_with_yolo(
    count_request: CountRequest,
    user: User = Depends(get_current_user),
    is_valid_subscription: bool = Depends(check_valid_subscription)
):
    original_image_url = await save_base64_image(count_request.base64_image)

    segmented_base64 = get_segmented_pipes(count_request.base64_image)
   
    if segmented_base64:
        # Pass the category_name to the counting function
        processed_img, count_text = count_objects_with_yolo(segmented_base64)
    else:
        # If no segmentation, pass the original image for object counting
        processed_img, count_text = count_objects_with_yolo(count_request.base64_image)

    if processed_img is None:
        print("No pipes detected.")
        processed_img, count_text = None, "0 objects"
        raise HTTPException(status_code=500, detail="Failed to process image.")
    

    processed_img = cv2.cvtColor(processed_img, cv2.COLOR_BGR2RGB)
    processed_pil = Image.fromarray(processed_img)
    processed_image_path = f"../static/processed_{uuid.uuid4()}.png"
    processed_pil.save(processed_image_path)

    bucket_name = "alvision-count"
    object_name = f"count/processed/processed_{uuid.uuid4()}.png"
    processed_image_url = aws_config.upload_to_s3(
        processed_image_path, bucket_name, object_name
    )

    current_utc_datetime = datetime.utcnow()
    ist_offset = timedelta(hours=5, minutes=30)
    current_ist_datetime = current_utc_datetime + ist_offset

    # Extract the numerical part from count_text
    count_value = int(count_text.split()[0])

    # Create the ObjectCount instance
    object_count = ObjectCount(
        object_count=count_value,
        timestamp=current_ist_datetime,
        original_image_url=original_image_url,
        processed_image_url=processed_image_url,
        user_id=user["_id"],
        category="nonTelescopic",
    )
    # Save the ObjectCount instance to the database
    await db["object_counts"].insert_one(object_count.model_dump(by_alias=True))

    os.remove(processed_image_path)

    return ObjectCountResponse(object_count=object_count)

