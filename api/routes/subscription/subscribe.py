import logging
from fastapi import FastAPI, HTTPException, Depends, APIRouter, Request
from typing import List, Optional
import razorpay
from pydantic import BaseModel, validator
from razorpay.errors import BadRequestError, SignatureVerificationError
from schemas import User, db
from core.oauth2 import get_current_user
from config import settings
from core.utils import check_admin_user
from fastapi.responses import JSONResponse
import time
from datetime import datetime

router = APIRouter(
    prefix="/subscribe",
    tags=["Subscriptions"],
)

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Razorpay client
client = razorpay.Client(auth=(settings.TEST_RAZORPAY_API_KEY, settings.TEST_RAZORPAY_SECRET_KEY))

# Pydantic models

class SubscriptionDetails(BaseModel):
    plan_id: str
    subscription_type: str  # "monthly", "quarterly", "half-yearly", "yearly"
    currency: str = 'INR'

    @validator('subscription_type')
    def validate_subscription_type(cls, v):
        allowed_types = {"monthly", "quarterly", "half-yearly", "yearly"}
        if v not in allowed_types:
            raise ValueError(f"Invalid subscription type. Allowed types: {allowed_types}")
        return v


class SubscriptionResponse(BaseModel):
    subscription_id: str
    user_id: str
    plan_id: str
    amount: int
    customer_email: str
    status: str
    created_at: str  # Expecting a formatted string now
    payment_link: Optional[str] = None
    updated_at: Optional[str] = None
    cancelled_at: Optional[str] = None




# 2. Subscribe to a plan (User selects plan and enters payment details)
@router.post("/subscribe-services", response_model=SubscriptionResponse)
async def subscribe_services(
    subscription_details: SubscriptionDetails,
    current_user: User = Depends(get_current_user)
):
    """
    The user subscribes to a selected plan. Payment is handled, and a subscription is created.
    """
    try:
        # Fetch plan details from MongoDB
        plan = await db.plans.find_one({"razorpay_plan_id": subscription_details.plan_id})
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        # Check for existing active subscription for the same plan
        existing_subscription = await db.subscriptions.find_one({
            "user_id": current_user["_id"],
            "plan_id": subscription_details.plan_id,
            "status": "active"
        })
        if existing_subscription:
            raise HTTPException(status_code=400, detail="Active subscription for this plan already exists")

        # Determine total amount based on the subscription type
        multiplier = {'monthly': 1, 'quarterly': 3, 'half-yearly': 6, 'yearly': 12}.get(subscription_details.subscription_type)
        total_amount = plan['amount'] * multiplier  # Calculate total amount

        # Create the subscription in Razorpay (initially set status to pending)
        subscription = client.subscription.create({
            'plan_id': subscription_details.plan_id,
            'total_count': multiplier,
            'customer_notify': 1,
            'notes': {
                'created_by': current_user['email']
            }
        })

        # Extract the payment link from the subscription response
        payment_link = subscription.get('short_url')

        # Get the current timestamp as created_at
        created_at = time.time()

        # Calculate start_date and end_date based on created_at and subscription_type
        start_date, end_date = calculate_dates(created_at, subscription_details.subscription_type)

        # Prepare subscription data to save to the database
        subscription_data = {
            'subscription_id': subscription['id'],
            'user_id': str(current_user["_id"]),  # Convert ObjectId to string
            'plan_id': subscription_details.plan_id,
            'amount': total_amount,
            'customer_email': current_user["email"],
            'status': 'pending',  # Initial status set to pending
            'created_at': created_at,
            'start_date': start_date,  # Calculated start date
            'end_date': end_date,      # Calculated end date
            'payment_link': payment_link,
            'subscription_type': subscription_details.subscription_type
        }

        # Save subscription to MongoDB
        result = await db.subscriptions.insert_one(subscription_data)

        # Ensure MongoDB's _id is also converted
        subscription_data["_id"] = str(result.inserted_id)

        return JSONResponse(content=subscription_data)

    except BadRequestError as e:
        logger.error(f"Error creating subscription: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error creating subscription: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred")




class CancelSubscriptionRequest(BaseModel):
    old_plan_id: str

# Route to cancel the old subscription
@router.post("/cancel-old-subscription")
async def cancel_old_subscription_route(
    cancel_request: CancelSubscriptionRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Route to cancel an old active subscription when upgrading to a new plan.
    """
    try:
        # Call the function to cancel the old subscription
        await cancel_old_subscription(current_user["_id"], cancel_request.old_plan_id)
        return {"status": "success", "message": "Old subscription cancelled successfully"}
    except HTTPException as e:
        logger.error(f"HTTPException: {str(e.detail)}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while cancelling the old subscription")

# The original function for canceling the old subscription
async def cancel_old_subscription(user_id: str, old_plan_id: str):
    try:
        # Fetch the old subscription from the database
        subscription = await db.subscriptions.find_one({"user_id": user_id, "plan_id": old_plan_id, "status": "active"})
        
        if subscription:
            # Cancel the old subscription in Razorpay
            client.subscription.cancel(subscription['subscription_id'])
            logger.info(f"Cancelled old subscription {subscription['subscription_id']} for user {user_id}")
            
            # Update the subscription status in the database
            await db.subscriptions.update_one({"subscription_id": subscription['subscription_id']}, {"$set": {"status": "cancelled"}})
        else:
            logger.info(f"No active subscription found for user {user_id} and plan {old_plan_id}")

    except Exception as e:
        logger.error(f"Error in cancelling old subscription: {str(e)}")
        raise HTTPException(status_code=500, detail="Error cancelling old subscription")



def format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime('%d-%m-%Y %H:%M:%S')

@router.get("/list_subscriptions", response_model=List[SubscriptionResponse])
async def list_user_subscriptions(
    current_user: User = Depends(get_current_user)
):
    try:
        # Fetch subscriptions for the current user from MongoDB
        subscriptions = await db.subscriptions.find({"user_id": current_user["_id"]}).to_list(length=None)
        
        # Format the timestamps
        for subscription in subscriptions:
            subscription['created_at'] = format_timestamp(subscription['created_at'])
            if 'updated_at' in subscription:
                subscription['updated_at'] = format_timestamp(subscription['updated_at'])
            if 'cancelled_at' in subscription:
                subscription['cancelled_at'] = format_timestamp(subscription['cancelled_at'])

        return subscriptions
    except Exception as e:
        logger.error(f"Error fetching subscriptions for user: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred while fetching subscriptions")
    




##################################################################################################################################################

from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Optional

class SubscriptionDetailResponse(BaseModel):
    subscription_id: str
    plan_name: str
    services: List[str]  # List of services associated with the plan
    status: str
    start_date: Optional[datetime]  # Make start_date optional
    end_date: Optional[datetime]    # Make end_date optional


# Function to calculate subscription dates based on created_at and subscription_type
def calculate_dates(created_at: float, subscription_type: str) :
    # Convert timestamp to datetime
    start_date = datetime.fromtimestamp(created_at)

    # Determine the duration based on subscription type
    if subscription_type == "monthly":
        end_date = start_date + timedelta(days=30)
    elif subscription_type == "quarterly":
        end_date = start_date + timedelta(days=90)
    elif subscription_type == "half-yearly":
        end_date = start_date + timedelta(days=180)
    elif subscription_type == "yearly":
        end_date = start_date + timedelta(days=365)
    else:
        end_date = None  # You can handle other types like 'quarterly' here if needed

    return start_date, end_date


@router.get("/subscriptions/active", response_model=List[SubscriptionDetailResponse])
async def get_active_subscriptions(
    current_user: User = Depends(get_current_user)
):
    """
    Fetches all active subscriptions of the current user and returns details about each subscription.
    """
    try:
        # Fetch user's active subscriptions from the database
        user_subscriptions = await db.subscriptions.find({
            "user_id": current_user["_id"], 
            "status": "active"
        }).to_list(length=None)

        if not user_subscriptions:
            raise HTTPException(status_code=404, detail="No active subscriptions found.")

        active_subscription_details = []

        # Loop through each subscription and fetch the plan details
        for subscription in user_subscriptions:
            plan_id = subscription.get("plan_id")
            
            # Fetch plan details (assuming you have a plans collection in the database)
            plan = await db.plans.find_one({"razorpay_plan_id": plan_id})
            if not plan:
                raise HTTPException(status_code=404, detail=f"Plan not found for subscription {subscription['subscription_id']}")

            # Fetch services related to the plan (this could be part of the plan document)
            services = plan.get("services", [])

            # Calculate start_date and end_date based on created_at and subscription_type
            created_at = subscription.get("created_at")
            subscription_type = subscription.get("subscription_type", "yearly")
            
            start_date, end_date = calculate_dates(created_at, subscription_type)

            # Create the response for each active subscription
            subscription_detail = SubscriptionDetailResponse(
                subscription_id=subscription["subscription_id"],
                plan_name=plan["name"],
                services=services,
                status=subscription["status"],
                start_date=start_date,  # Calculated start_date
                end_date=end_date       # Calculated end_date
            )
            
            active_subscription_details.append(subscription_detail)

        return active_subscription_details

    except Exception as e:
        logger.error(f"Error fetching active subscriptions: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching active subscriptions")
