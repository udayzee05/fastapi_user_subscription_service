import logging
from fastapi import Depends, HTTPException
from api.core.db import db
from api.core.oauth2 import get_current_user
from bson import ObjectId
from datetime import date, datetime
from fastapi import APIRouter

from bson import ObjectId
from fastapi import HTTPException, Depends
from api.core.oauth2 import get_current_user


router = APIRouter(prefix="/data-manipulation", tags=["Count Data Manipulation"])

# Logging configuration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@router.get("/no-of-requests")
async def get_no_of_requests(date: date, category: str = None):
    # Convert the `date` into an ISODate format to match the timestamp field
    start_of_day = datetime.combine(date, datetime.min.time())  # 00:00:00 of the date
    end_of_day = datetime.combine(date, datetime.max.time())  # 23:59:59 of the date
    
    # Build the query for date range
    query = {
        "timestamp": {
            "$gte": start_of_day,
            "$lte": end_of_day
        }
    }

    # If a category is provided, add it to the query
    if category:
        query["category"] = category

    # Print the query for debugging purposes
    print(f"Querying with: {query}")

    # Query the `object_counts` collection with the built query
    results = await db.object_counts.find(query).to_list(length=None)

    # Print the results for debugging purposes
    print(f"Found object counts: {results}")

    # Get the number of records (number of documents found)
    record_count = len(results)

    # Print the final record count for debugging
    print(f"Number of records: {record_count}")

    return {"date": date.isoformat(), "category": category, "total_records": record_count}


@router.get("/user-data")
async def get_user_data_by_date_and_category(
    date: date, 
    category: str = None,  # Make category optional by setting default to None
    user: dict = Depends(get_current_user)  # Get the current logged-in user as a dict
):
    """
    Retrieve records for the logged-in user filtered by date and optionally category.
    """
    # Convert the `date` into an ISODate format to match the timestamp field
    start_of_day = datetime.combine(date, datetime.min.time())  # 00:00:00 of the date
    end_of_day = datetime.combine(date, datetime.max.time())  # 23:59:59 of the date
    
    # Build the query to filter by user_id and date
    query = {
        "user_id": ObjectId(user["_id"]),  # Access the user ID from the dictionary
        "timestamp": {
            "$gte": start_of_day,
            "$lte": end_of_day
        }
    }

    # If category is provided, add it to the query
    if category:
        query["category"] = category

    # Print the query for debugging purposes
    print(f"Querying with: {query}")

    # Query the `object_counts` collection for the logged-in user
    results = await db.object_counts.find(query).to_list(length=None)

    # Convert ObjectId fields to strings for JSON serialization
    for result in results:
        result["_id"] = str(result["_id"])
        result["user_id"] = str(result["user_id"])

    # Print the results for debugging purposes
    print(f"Found records: {results}")

    # Get the number of records found
    record_count = len(results)

    # Return the results and the total number of records
    return {
        "date": date.isoformat(),
        "category": category if category else "All",  # Return 'All' if no category provided
        "user_id": str(user["_id"]),  # Return the user ID in the response
        "total_records": record_count,
        "records": results  # You can return the actual records if needed
    }




@router.patch("/manual-count")
async def update_count(
    increment: int, 
    processed_image_url: str, 
    user: dict = Depends(get_current_user)  # Retrieve the current logged-in user
):
    """
    Update the count and processed image URL for the specified category.
    """
    # Access the user's `user_id`
    user_id = ObjectId(user["_id"])

    # Query the last record for the user and category
    last_record = await db.object_counts.find_one(
        {"user_id": user_id},
        sort=[("timestamp", -1)]  # Sort by timestamp to get the latest record
    )

    if not last_record:
        raise HTTPException(status_code=404, detail="No records found for category")

    # Extract the current count and increment it
    current_count = last_record["object_count"]
    new_count = current_count + increment

    # Update the record in MongoDB with the new count and processed image URL
    update_result = await db.object_counts.update_one(
        {"_id": last_record["_id"]},
        {"$set": {
            "object_count": new_count,
            "processed_image_url": processed_image_url
        }}
    )

    if update_result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update the record.")

    # Log the successful update
    logger.info(f"Record updated successfully with new count: {new_count}")

    return {"msg": f"Count and processed image URL updated", "updated_count": new_count}
