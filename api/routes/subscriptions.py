import logging
from fastapi import FastAPI, HTTPException, Depends, APIRouter, Request
from typing import List, Optional
import razorpay
from pydantic import BaseModel,validator
from razorpay.errors import BadRequestError, SignatureVerificationError
from schemas import User, db
from core.oauth2 import get_current_user
from config import settings
from core.utils import check_admin_user
from fastapi.responses import JSONResponse
import time
from datetime import datetime

from bson import ObjectId

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Initialize Razorpay client
client = razorpay.Client(auth=(settings.TEST_RAZORPAY_API_KEY, settings.TEST_RAZORPAY_SECRET_KEY))

# Pydantic models
class PlanDetails(BaseModel):
    name: str
    amount: int  # Amount in INR
    period: str
    interval: int
    description: Optional[str] = None

from pydantic import BaseModel, validator

class SubscriptionDetails(BaseModel):
    plan_id: str
    subscription_type: str  # "monthly", "quarterly", "half-yearly", "yearly"
    offer_code: Optional[str] = None
    currency: str = 'INR'

    @validator('subscription_type')
    def validate_subscription_type(cls, v):
        allowed_types = {"monthly", "quarterly", "half-yearly", "yearly"}
        if v not in allowed_types:
            raise ValueError(f"Invalid subscription type. Allowed types: {allowed_types}")
        return v

class PlanResponse(BaseModel):
    id: str
    period: str
    interval: int
    item: dict
    notes: dict

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

router = APIRouter(
    prefix="/subscriptions",
    tags=["Subscriptions"]
)

@router.get("/health")
async def health_check():
    return {"status": "healthy"}

@router.post("/create-plan", response_model=PlanResponse)
async def create_subscription_plan(
    plan_details: PlanDetails,
    current_user: User = Depends(check_admin_user)
):
    try:
        plan = client.plan.create({
            'period': plan_details.period,
            'interval': plan_details.interval,
            'item': {
                'name': plan_details.name,
                'amount': plan_details.amount * 100,  # Convert to paise (INR)
                'currency': 'INR',
                'description': plan_details.description,
            },
            'notes': {
                'created_by': current_user.name
            }
        })

        # Save plan to MongoDB
        await db.plans.insert_one({
            'razorpay_plan_id': plan['id'],
            'name': plan_details.name,
            'amount': plan_details.amount,
            'period': plan_details.period,
            'interval': plan_details.interval,
            'description': plan_details.description,
            'created_by': current_user.name
        })

        return JSONResponse(content=plan)
    except BadRequestError as e:
        logger.error(f"Error creating Razorpay plan: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error creating Razorpay plan: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred")

@router.get("/plans", response_model=List[PlanResponse])
async def list_plans():
    try:
        plans = client.plan.all()
        return plans['items']
    except BadRequestError as e:
        logger.error(f"Error fetching plans: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error fetching plans: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred")
   
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

        # Determine the total count and amount based on the subscription type
        if subscription_details.subscription_type == 'monthly':
            total_count = 1
            multiplier = 1
        elif subscription_details.subscription_type == 'quarterly':
            total_count = 3
            multiplier = 3
        elif subscription_details.subscription_type == 'half-yearly':
            total_count = 6
            multiplier = 6
        elif subscription_details.subscription_type == 'yearly':
            total_count = 12
            multiplier = 12
        else:
            raise HTTPException(status_code=400, detail="Invalid subscription type")

        total_amount = plan['amount'] * multiplier  # Calculate total amount based on the type

        # Create the subscription in Razorpay
        subscription = client.subscription.create({
            'plan_id': subscription_details.plan_id,
            'total_count': total_count,
            'customer_notify': 1,
            'addons': [],
            'notes': {
                'created_by': current_user['email']
            }
        })

        # Extract the payment link from the subscription response
        payment_link = subscription.get('short_url')

        # Prepare subscription data to save to the database
        subscription_data = {
            'subscription_id': subscription['id'],
            'user_id': str(current_user["_id"]),  # Convert ObjectId to string
            'plan_id': subscription_details.plan_id,
            'amount': total_amount,
            'customer_email': current_user["email"],
            'status': 'pending',
            'created_at': time.time(),
            'payment_link': payment_link,  # Use the payment link provided by Razorpay
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
    except HTTPException as e:
        logger.error(f"HTTP error: {str(e.detail)}")
        raise e
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred")

@router.post("/webhook")
async def handle_webhook(request: Request):
    headers = request.headers
    logger.info(f"Request headers: {headers}")

    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    webhook_signature = headers.get('X-Razorpay-Signature')
    user_agent = headers.get('User-Agent')

    if webhook_signature is None:
        if 'Razorpay-Webhook' not in user_agent:
            logger.error("Missing X-Razorpay-Signature header or invalid User-Agent")
            raise HTTPException(status_code=400, detail="This endpoint is for Razorpay webhooks only.")
        else:
            logger.error("Missing X-Razorpay-Signature header")
            raise HTTPException(status_code=400, detail="Missing X-Razorpay-Signature header")

    webhook_body = await request.body()
    logger.info(f"Request body: {webhook_body.decode('utf-8')}")

    try:
        # Convert the webhook_body to a string
        webhook_body_str = webhook_body.decode('utf-8')

        # Verify webhook signature
        client.utility.verify_webhook_signature(
            webhook_body_str, webhook_signature, webhook_secret
        )
    except SignatureVerificationError:
        logger.error("Invalid webhook signature")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    webhook_data = await request.json()
    event = webhook_data.get("event")
    logger.info(f"Received event: {event}")

    if event == "payment.captured":
        payment_entity = webhook_data["payload"]["payment"]["entity"]
        payment_id = payment_entity["id"]
        amount = payment_entity["amount"]

        subscription_id = payment_entity.get("subscription_id")
        if subscription_id:
            # Process subscription payment
            await update_subscription_status(subscription_id, payment_id, amount, status="active")
            return JSONResponse(content={"status": "success"}, status_code=200)
        else:
            # Handle payments not linked to a subscription
            logger.warning(f"No subscription_id found for payment {payment_id}")
            return JSONResponse(content={"status": "no subscription_id in payment"}, status_code=200)

    elif event == "payment.failed":
        payment_entity = webhook_data["payload"]["payment"]["entity"]
        payment_id = payment_entity["id"]
        amount = payment_entity["amount"]

        subscription_id = payment_entity.get("subscription_id")
        if subscription_id:
            await update_subscription_status(subscription_id, payment_id, amount, status="failed")
        else:
            logger.warning(f"No subscription_id found for failed payment {payment_id}")

        return JSONResponse(content={"status": "failed"}, status_code=200)

    # Log other events
    logger.info(f"Unhandled event type: {event}")

    # Respond appropriately for unhandled events
    return JSONResponse(content={"status": f"event {event} not handled"}, status_code=200)


@router.post("/cancel-subscription")
async def cancel_subscription(
    subscription_id: str,
    current_user: User = Depends(get_current_user)
):
    try:
        # Cancel the subscription in Razorpay
        logger.info(f"Cancelling subscription in Razorpay for subscription_id: {subscription_id}")
        subscription = client.subscription.cancel(subscription_id)
        
        # Update the subscription status in MongoDB
        logger.info(f"Updating subscription status in MongoDB for subscription_id: {subscription_id}")
        result = await db.subscriptions.update_one(
            {"subscription_id": subscription_id},
            {"$set": {"status": "cancelled", "cancelled_at": time.time()}}
        )

        if result.modified_count:
            logger.info(f"Subscription status updated to cancelled for subscription_id: {subscription_id}")
            return JSONResponse(content={"status": "subscription cancelled"}, status_code=200)
        else:
            logger.error(f"Failed to update subscription status in MongoDB for subscription_id: {subscription_id}")
            raise HTTPException(status_code=500, detail="Failed to update subscription status in MongoDB")

    except BadRequestError as e:
        logger.error(f"Error cancelling subscription: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error cancelling subscription: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred")

def format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime('%d-%m-%Y %H:%M:%S')

@router.get("/subscriptions", response_model=List[SubscriptionResponse])
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



@router.post("/refresh-subscriptions", response_model=List[SubscriptionResponse])
async def refresh_subscriptions(
    current_user: User = Depends(get_current_user)
):
    try:
        # Fetch subscriptions for the current user from MongoDB
        subscriptions = await db.subscriptions.find({"user_id": current_user["_id"]}).to_list(length=None)
        updated_subscriptions = []
        for subscription in subscriptions:
            razorpay_subscription = client.subscription.fetch(subscription['subscription_id'])
            if razorpay_subscription['status'] != subscription['status']:
                result = await db.subscriptions.update_one(
                    {"subscription_id": subscription['subscription_id']},
                    {"$set": {"status": razorpay_subscription['status']}}
                )
                if result.modified_count:
                    logger.info(f"Updated subscription status to {razorpay_subscription['status']} for subscription_id: {subscription['subscription_id']}")
                    subscription['status'] = razorpay_subscription['status']
                else:
                    logger.error(f"Failed to update subscription status for subscription_id: {subscription['subscription_id']}")

            # Convert the timestamps to strings before adding to the response
            subscription['created_at'] = format_timestamp(subscription['created_at'])
            if 'updated_at' in subscription:
                subscription['updated_at'] = format_timestamp(subscription['updated_at'])
            if 'cancelled_at' in subscription:
                subscription['cancelled_at'] = format_timestamp(subscription['cancelled_at'])

            updated_subscriptions.append(subscription)
        return updated_subscriptions
    except Exception as e:
        logger.error(f"Error during subscription refresh: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred while refreshing subscriptions")

async def update_subscription_status(subscription_id: str, payment_id: str, amount: int, status: str):
    try:
        # Fetch the subscription from MongoDB
        logger.info(f"Fetching subscription from database for subscription_id: {subscription_id}")
        subscription = await db.subscriptions.find_one({'subscription_id': subscription_id})
        if not subscription:
            logger.error(f"Subscription not found for subscription_id: {subscription_id}")
            raise HTTPException(status_code=404, detail="Subscription not found")

        # Update the subscription status in MongoDB
        result = await db.subscriptions.update_one(
            {"subscription_id": subscription_id},
            {"$set": {"status": status, "payment_id": payment_id, "amount": amount, "updated_at": time.time()}}
        )

        if result.modified_count:
            logger.info(f"Subscription status updated to {status} for subscription_id: {subscription_id}")
        else:
            logger.error(f"Failed to update subscription status to {status} in MongoDB for subscription_id: {subscription_id}")

    except Exception as e:
        logger.error(f"Error in update_subscription_status: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating subscription status")

