
import logging

from fastapi import Depends, HTTPException
from api.models.user import User
from api.core.db import db
from api.models.mildSteelBars import ObjectCount, ObjectCountResponse,CountRequest
from api.core.oauth2 import get_current_user
from api.core.utils import valid_subscription_for_service, save_base64_image,check_valid_subscription
from PIL import Image
import cv2

import uuid
from datetime import datetime,timedelta
import os
from api.services.metalSquarePipe import count_objects_with_yolo, get_segmented_pipes
from api.core.aws import AWSConfig
from fastapi import APIRouter

SERVICE_NAME = "metalSqaurePipe"

router = APIRouter(prefix="/count", tags=[f"{SERVICE_NAME}"])


# Logging configuration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


aws_config = AWSConfig()



@router.post(f"/{SERVICE_NAME}")
async def count_with_yolo(
    count_request: CountRequest,
    user: User = Depends(get_current_user),
    is_valid_subscription: bool = Depends(check_valid_subscription),
):
    """
    Endpoint to count objects using YOLO for mild steel bars. Requires the user to have an active subscription 
    for the 'mildSteelBars' service.
    """
    # Ensure the user has a valid subscription before proceeding
    if not is_valid_subscription:
        return {f"message": "You do not have an active subscription for the mildSteelBars service."}


    # Save the original base64 image to S3
    original_image_url = await save_base64_image(count_request.base64_image, SERVICE_NAME)

    # Perform image segmentation
    segmented_base64 = get_segmented_pipes(count_request.base64_image)
   
    if segmented_base64:
        # Pass the segmented image to YOLO for object counting
        processed_img, count_text = count_objects_with_yolo(segmented_base64)
    else:
        # If no segmentation is found, pass the original image for counting
        processed_img, count_text = count_objects_with_yolo(count_request.base64_image)

    if processed_img is None:
        print("No pipes detected.")
        raise HTTPException(status_code=500, detail="Failed to process image.")
    
    # Process the image and upload it to S3
    processed_img = cv2.cvtColor(processed_img, cv2.COLOR_BGR2RGB)
    processed_pil = Image.fromarray(processed_img)
    processed_image_path = f"../static/processed_{uuid.uuid4()}.png"
    processed_pil.save(processed_image_path)

    # Upload processed image to S3
    bucket_name = "alvision-count"
    object_name = f"count/{SERVICE_NAME}/processed/processed_{uuid.uuid4()}.png"
    processed_image_url = aws_config.upload_to_s3(
        processed_image_path, bucket_name, object_name
    )

    # Get the current IST timestamp
    current_utc_datetime = datetime.utcnow()
    ist_offset = timedelta(hours=5, minutes=30)
    current_ist_datetime = current_utc_datetime + ist_offset

    # Extract the count value
    count_value = int(count_text.split()[0])

    # Create and save the ObjectCount instance
    object_count = ObjectCount(
        object_count=count_value,
        timestamp=current_ist_datetime,
        original_image_url=original_image_url,
        processed_image_url=processed_image_url,
        user_id=user["_id"],
        category=SERVICE_NAME,
    )
    
    # Save the ObjectCount instance to the database
    await db["object_counts"].insert_one(object_count.model_dump(by_alias=True))

    # Clean up the local processed image file
    os.remove(processed_image_path)

    # Return the response
    return ObjectCountResponse(object_count=object_count)
