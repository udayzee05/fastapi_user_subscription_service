from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime, timedelta
from api.core.db import db
from api.services.mildSteelBars import count_objects_with_yolo, get_segmented_pipes
from api.core.aws import AWSConfig
import uuid
from api.models.mildSteelBars import ObjectCount, ObjectCountResponse
from api.core.oauth2 import get_current_user
from api.core.utils import save_base64_image,check_valid_subscription

import logging

from fastapi import APIRouter

import cv2
from PIL import Image
import os

SERVICE_NAME = "testServe"

router = APIRouter(prefix="/count", tags=["testServe"])


# Logging configuration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

aws_config = AWSConfig()

class CountRequest(BaseModel):
    base64_image: str
    work_order_id: str   # Work order to associate with the object count
    order_index: int = 0  # The specific order index within the work order, default to 0 if not specified

@router.post(f"/count/{SERVICE_NAME}")
async def count_with_yolo(
    count_request: CountRequest, 
    user: dict = Depends(get_current_user),
    is_valid_subscription: bool = Depends(check_valid_subscription)
):
    """
    Count objects for '{SERVICE_NAME}' service and associate result with a work order.
    """
    if not is_valid_subscription:
        return {"message": "You do not have an active subscription for the NonTelescopicPipe service."}


    # Fetch the work order
    work_order = await db["work_orders"].find_one(
        {"work_order_id": count_request.work_order_id, "user_id": ObjectId(user["_id"])}
    )

    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    # Ensure the order index exists
    if count_request.order_index >= len(work_order.get("orders", [])):
        raise HTTPException(status_code=400, detail="Invalid order index")

    # Save the original base64 image to S3
    original_image_url = await save_base64_image(count_request.base64_image, SERVICE_NAME)

    # Segment and count objects using YOLO
    segmented_base64 = get_segmented_pipes(count_request.base64_image)
    processed_img, count_text = count_objects_with_yolo(segmented_base64 or count_request.base64_image)

    if processed_img is None:
        raise HTTPException(status_code=500, detail="No objects detected in the image.")

    # Process the image and upload to S3
    processed_img = cv2.cvtColor(processed_img, cv2.COLOR_BGR2RGB)
    processed_pil = Image.fromarray(processed_img)
    processed_image_path = f"../static/processed_{uuid.uuid4()}.png"
    processed_pil.save(processed_image_path)

    bucket_name = "alvision-count"
    object_name = f"count/{SERVICE_NAME}/processed/processed_{uuid.uuid4()}.png"
    processed_image_url = aws_config.upload_to_s3(processed_image_path, bucket_name, object_name)

    # Get current IST time
    current_utc_datetime = datetime.utcnow()
    ist_offset = timedelta(hours=5, minutes=30)
    current_ist_datetime = current_utc_datetime + ist_offset

    # Extract the count value
    count_value = int(count_text.split()[0])

    # Create ObjectCount instance and save to DB
    object_count = ObjectCount(
        object_count=count_value,
        timestamp=current_ist_datetime,
        original_image_url=original_image_url,
        processed_image_url=processed_image_url,
        user_id=user["_id"],
        category=SERVICE_NAME,
        work_order_id=work_order["work_order_id"],
        order_index=count_request.order_index
    )
    inserted_count = await db["object_counts"].insert_one(object_count.model_dump(by_alias=True))

    # Update the order with the ObjectCount ID and qty_ordered
    object_count_id = inserted_count.inserted_id
    update_order_result = await db["work_orders"].update_one(
        {
            "work_order_id": count_request.work_order_id,
            f"orders.{count_request.order_index}": {"$exists": True}
        },
        {
            "$set": {
                f"orders.{count_request.order_index}.qty_ordered": count_value,
                f"orders.{count_request.order_index}.object_count_id": object_count_id  # Store reference
            }
        }
    )

    if update_order_result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update order with ObjectCount ID")

    # Clean up local processed image file
    os.remove(processed_image_path)

    # Return response
    return {
        "message": "Object counting completed",
        "object_count_id": str(object_count_id),
        "object_count": object_count
    }
