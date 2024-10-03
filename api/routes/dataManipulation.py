
import logging
from fastapi import Depends, Request, HTTPException
from schemas import User,db
from core.oauth2 import get_current_user
from bson import ObjectId
from datetime import date
from typing import List, Dict
from fastapi import APIRouter


router = APIRouter(prefix="/data-manipulation", tags=["Count Data Manipulation"])

# Logging configuration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)



@router.patch("/manual-count")
async def update_count(
    increment: int, processed_image_url: str, user: User = Depends(get_current_user),
):
    if not user.counts:
        raise HTTPException(status_code=404, detail="No records found for this user.")

    # Retrieve the last count record
    last_record = user.counts[-1]

    # Extract the numeric part and the suffix from the last count
    parts = last_record["Count"]
    # if len(parts) < 2 or not parts[0].isdigit():
    #     raise HTTPException(status_code=400, detail="Current count format is invalid.")

    # Calculate the new count
    new_count = parts+ increment
    updated_count = f"{new_count}"  # Assuming the suffix is always the same and at index 1

    # Update the count in the last record
    last_record["Count"] = updated_count
    last_record["Processed_Image_URL"] = processed_image_url

    # Save the updated user document
    await user.update({"$set": {"counts": user.counts}})
    logger.info("Last record updated")

    return {"msg": "Count and processed image URL updated", "Last_Record": last_record}




@router.get("/no-of-requests")
async def get_no_of_requests(date: date):
    users = await User.find().to_list()
    total_count = sum(
        entry["count"]
        for user in users
        for entry in user.count_requests
        if entry.get("date") == date.isoformat()
    )
    return {"date": date.isoformat(), "total_count": total_count}



@router.get("/user-counts", response_model=List[Dict])
async def get_user_counts(user: User = Depends(get_current_user)):
    # filtered_counts = [count for count in user.counts if 'ID' in count]
    logger.info("Retrieving user counts")
    return user.counts

@router.get("/user-counts/{date}", response_model=List[Dict])
async def get_user_counts_by_date(
    date: date, user: User = Depends(get_current_user)
):
    # filtered_counts = [count for count in user.counts if count["Date"] == date.isoformat() and 'ID' in count]
    filtered_counts = [
        count for count in user.counts if count["Date"] == date.isoformat()
    ]
    logger.info(f"Retrieving user counts for date: {date}")
    return filtered_counts



@router.get("/user-category-counts", response_model=List[Dict])
async def get_user_category_counts(user: User = Depends(get_current_user)):
    """
    Route to count images and objects by category for the current user.
    """
    user_id = user.id  # Assuming `User` model contains the `id` field for user_id

    # MongoDB aggregation pipeline to count the images and objects processed by category
    pipeline = [
        {
            "$match": {
                "user_id": ObjectId(user_id)  # Filter by current user's ID
            }
        },
        {
            "$group": {
                "_id": "$category",  # Group by category
                "total_images_counted": {"$sum": 1},
                "total_object_count": {"$sum": "$object_count"}
            }
        },
        {
            "$project": {
                "_id": 0,
                "category": "$_id",
                "total_images_counted": 1,
                "total_object_count": 1
            }
        }
    ]

    results = list(db.object_counts.aggregate(pipeline))

    if not results:
        raise HTTPException(status_code=404, detail="No records found for this user.")

    return results