import logging
from fastapi import HTTPException, Depends, APIRouter
from typing import List
from razorpay.errors import BadRequestError
from api.core.db import db
from api.models.user import User
from api.core.oauth2 import get_current_user
from fastapi.responses import JSONResponse
import time
from datetime import datetime
from api.models.subscriptions import SubscriptionDetails, SubscriptionResponse,CancelSubscriptionRequest,SubscriptionDetailResponse
from api.core.razorpay import client

router = APIRouter(
    prefix="/subscribe",
    tags=["Subscriptions"],
)

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def format_datetime(dt: datetime) -> str:
    """
    Convert datetime object to string in '%Y-%m-%d %H:%M:%S' format.
    """
    return dt.strftime('%Y-%m-%d %H:%M:%S')

from datetime import datetime, timedelta
def calculate_total_count(plan_name: str):
    """
    Calculate the total count based on the plan name.
    Example plan names: "Metal Counting Monthly", "Metal Counting Quarterly", "Metal Counting Yearly"
    """
    if "monthly" in plan_name.lower():
        return 1200
    elif "quarterly" in plan_name.lower():
        return 400
    elif "half-yearly" in plan_name.lower():
        return 200
    elif "yearly" in plan_name.lower():
        return 100
    else:
        return 12
def calculate_dates_from_plan_name(plan_name: str):
    """
    Calculate the start_date and end_date based on the plan name.
    Example plan names: "Metal Counting Monthly", "Metal Counting Quarterly", "Metal Counting Yearly"
    """
    start_date = datetime.now()
    if "monthly" in plan_name.lower():
        end_date = start_date + timedelta(days=30)
    elif "quarterly" in plan_name.lower():
        end_date = start_date + timedelta(days=90)
    elif "half-yearly" in plan_name.lower():
        end_date = start_date + timedelta(days=180)
    elif "yearly" in plan_name.lower():
        end_date = start_date + timedelta(days=365)
    else:
        # Default to 30 days (monthly) if no duration is found in the name
        end_date = start_date + timedelta(days=30)

    return start_date, end_date


@router.post("/subscribe-services", response_model=SubscriptionResponse)
async def subscribe_services(
    subscription_details: SubscriptionDetails,
    current_user: User = Depends(get_current_user)
):
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
        
        # Determine total count based on the plan name
        total_count = calculate_total_count(plan['name'])
        # Create the subscription in Razorpay (initially set status to pending)
        subscription = client.subscription.create({
            'plan_id': subscription_details.plan_id,
            'customer_notify': 1,
            'total_count': total_count,
            'notes': {
                'created_by': current_user['email']
            }
        })

        # Extract the payment link from the subscription response
        payment_link = subscription.get('short_url')

        # Calculate the start and end date based on the plan name
        start_date, end_date = calculate_dates_from_plan_name(plan['name'])

        # Get the current timestamp as created_at
        created_at = time.time()

        # Prepare subscription data to save to the database
        subscription_data = {
            'subscription_id': subscription['id'],
            'user_id': str(current_user["_id"]),  # Convert ObjectId to string
            'plan_id': subscription_details.plan_id,
            'plan_name': plan['name'],
            'amount': plan['amount'],
            'customer_email': current_user["email"],
            'status': 'pending',  # Initial status set to pending
            'created_at': created_at,
            'start_date': start_date.strftime('%Y-%m-%d %H:%M:%S'),
            'end_date': end_date.strftime('%Y-%m-%d %H:%M:%S'),
            'payment_link': payment_link,
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


###########################################################################################################################################



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
        await cancel_old_subscription(current_user["_id"], cancel_request.subcription_id)
        return {"status": "success", "message": "Old subscription cancelled successfully"}
    except HTTPException as e:
        logger.error(f"HTTPException: {str(e.detail)}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while cancelling the old subscription")
    
async def cancel_old_subscription(user_id: str, subscription_id: str):
    try:
        # Debugging logs to ensure correct plan and subscription IDs
        logger.info(f"Attempting to cancel subscription for user {user_id} and subscription_id {subscription_id}")

        # Fetch the old subscription using subscription_id instead of plan_id
        subscription = await db.subscriptions.find_one({"user_id": user_id, "subscription_id": subscription_id, "status": "active"})

        if subscription:
            # Cancel the old subscription in Razorpay
            try:
                razorpay_subscription = client.subscription.cancel(subscription['subscription_id'])
                if razorpay_subscription['status'] != 'cancelled':
                    raise HTTPException(status_code=500, detail="Failed to cancel the subscription in Razorpay")
                logger.info(f"Cancelled old subscription {subscription['subscription_id']} for user {user_id}")
            except BadRequestError as e:
                logger.error(f"Error cancelling subscription in Razorpay: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Error cancelling subscription in Razorpay: {str(e)}")

            # Update the subscription status in the database
            await db.subscriptions.update_one(
                {"subscription_id": subscription['subscription_id']}, 
                {"$set": {"status": "cancelled"}}
            )

            # Remove the service from the user document
            await db.users.update_one(
                {"_id": user_id}, 
                {"$pull": {"subscribed_services": subscription['plan_name']}}  # Remove the plan name from the list
            )

        else:
            logger.info(f"No active subscription found for user {user_id} and subscription_id {subscription_id}")

    except BadRequestError as e:
        logger.error(f"Razorpay error in cancelling old subscription: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Razorpay error: {str(e)}")
    except Exception as e:
        logger.error(f"Error in cancelling old subscription: {str(e)}")
        raise HTTPException(status_code=500, detail="Error cancelling old subscription")


#############################################################################################################################


def format_timestamp(timestamp: float) -> str:
    """
    Convert a timestamp (float) to a formatted datetime string.
    """
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')


@router.get("/list_subscriptions", response_model=List[SubscriptionResponse])
async def list_user_subscriptions(
    current_user: User = Depends(get_current_user)
):
    try:
        # Fetch subscriptions for the current user from MongoDB
        subscriptions = await db.subscriptions.find({"user_id": current_user["_id"]}).to_list(length=None)

        updated_subscriptions = []

        # Loop through each subscription to fetch the latest status from Razorpay
        for subscription in subscriptions:
            subscription_id = subscription['subscription_id']

            try:
                # Fetch the latest subscription details from Razorpay
                razorpay_subscription = client.subscription.fetch(subscription_id)

                # Extract the latest status from Razorpay response
                latest_status = razorpay_subscription['status']

                # If the status has changed, update it in the local database
                if latest_status != subscription['status']:
                    await db.subscriptions.update_one(
                        {"subscription_id": subscription_id},
                        {"$set": {"status": latest_status}}
                    )
                    subscription['status'] = latest_status  # Update the local variable too

                # Format the timestamps from Razorpay or MongoDB if necessary
                subscription['created_at'] = format_timestamp(razorpay_subscription.get('created_at', subscription['created_at']))
                if 'updated_at' in razorpay_subscription:
                    subscription['updated_at'] = format_timestamp(razorpay_subscription['updated_at'])
                else:
                    subscription['updated_at'] = format_timestamp(subscription.get('updated_at', time.time()))

                if 'cancelled_at' in razorpay_subscription:
                    subscription['cancelled_at'] = format_timestamp(razorpay_subscription['cancelled_at'])
                elif 'cancelled_at' in subscription:
                    subscription['cancelled_at'] = format_timestamp(subscription['cancelled_at'])

            except Exception as e:
                logger.error(f"Error fetching subscription {subscription_id} from Razorpay: {str(e)}")
                continue  # Skip this subscription if there's an error fetching the latest status

            updated_subscriptions.append(subscription)

        return updated_subscriptions

    except Exception as e:
        logger.error(f"Error fetching subscriptions for user: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred while fetching subscriptions")





##################################################################################################################################################


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
            "status": "active"  # Only fetch active subscriptions
        }).to_list(length=None)

        # If no active subscriptions are found, return an empty list
        if not user_subscriptions:
            return []  # Return empty list if no active subscriptions are found

        active_subscription_details = []

        # Loop through each subscription and fetch the plan details
        for subscription in user_subscriptions:
            plan_id = subscription.get("plan_id")
            
            # Fetch plan details (assuming you have a plans collection in the database)
            plan = await db.plans.find_one({"razorpay_plan_id": plan_id})
            if not plan:
                raise HTTPException(status_code=404, detail=f"Plan not found for subscription {subscription['subscription_id']}")

            # Extract start_date and end_date from the subscription
            start_date = subscription.get("start_date")
            end_date = subscription.get("end_date")

            # Convert start_date and end_date to datetime objects if they exist
            if start_date:
                start_date = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
            if end_date:
                end_date = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")

            # Create the response for each active subscription
            subscription_detail = SubscriptionDetailResponse(
                subscription_id=subscription["subscription_id"],
                plan_name=plan["name"],
                status=subscription["status"],
                start_date=start_date,  # Use the calculated start_date
                end_date=end_date        # Use the calculated end_date
            )
            
            active_subscription_details.append(subscription_detail)

        return active_subscription_details

    except Exception as e:
        logger.error(f"Error fetching active subscriptions: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching active subscriptions")




@router.get("/subscriptions/sync")
async def sync_subscriptions_on_login(
    current_user: User = Depends(get_current_user)
):
    """
    Fetches all subscriptions of the current user, syncs their status from Razorpay, and updates the local database.
    This route can be triggered when the user logs in, ensuring the database and Razorpay dashboard are in sync.
    """
    try:
        # Fetch all subscriptions for the current user from the database
        user_subscriptions = await db.subscriptions.find({
            "user_id": current_user["_id"]
        }).to_list(length=None)

        if not user_subscriptions:
            return {"message": "No subscriptions found to sync."}

        # Loop through each subscription and fetch the latest status from Razorpay
        for subscription in user_subscriptions:
            subscription_id = subscription.get("subscription_id")
            
            try:
                # Fetch the latest subscription details from Razorpay
                razorpay_subscription = client.subscription.fetch(subscription_id)
                
                # Extract the latest status from Razorpay response
                latest_status = razorpay_subscription['status']

                # If the status has changed, update it in the local database
                if latest_status != subscription['status']:
                    await db.subscriptions.update_one(
                        {"subscription_id": subscription_id},
                        {"$set": {"status": latest_status}}
                    )
                    logger.info(f"Updated subscription {subscription_id} status to {latest_status} for user {current_user['_id']}")

            except Exception as e:
                logger.error(f"Error fetching subscription {subscription_id} from Razorpay: {str(e)}")
                continue  # Skip this subscription if there's an error fetching the latest status

        return {"message": "Subscriptions synced successfully."}

    except Exception as e:
        logger.error(f"Error syncing subscriptions for user {current_user['_id']}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error syncing subscriptions")
