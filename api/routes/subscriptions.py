import logging
from fastapi import FastAPI, HTTPException, Depends, APIRouter, Request
from typing import List, Optional
import razorpay
from pydantic import BaseModel, validator
from razorpay.errors import BadRequestError, SignatureVerificationError
from api.core.db import db
from api.models.user import User
from api.core.oauth2 import get_current_user
from api.config import settings
from api.core.utils import check_admin_user
from fastapi.responses import JSONResponse
import time
from datetime import datetime

router = APIRouter(
    prefix="/subscriptions",
    tags=["Subscriptionss"]
)

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Razorpay client
client = razorpay.Client(auth=(settings.TEST_RAZORPAY_API_KEY, settings.TEST_RAZORPAY_SECRET_KEY))

# Pydantic models
class PlanDetails(BaseModel):
    name: str
    amount: int  # Amount in INR
    period: str
    interval: int
    description: Optional[str] = None

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

# 1. List all subscription plans (User landing page & plan selection)
@router.get("/plans", response_model=List[PlanResponse])
async def list_plans():
    """
    Fetch subscription plans from Razorpay and store them in the database if they don't already exist.
    """
    try:
        # Fetch plans from Razorpay
        plans = client.plan.all()
        updated_plans = []

        for plan in plans['items']:
            # Ensure 'notes' is always a dictionary
            if not isinstance(plan.get('notes'), dict):
                plan['notes'] = {}  # Set 'notes' to an empty dictionary if it's missing or invalid

            # Check if the plan already exists in the database
            existing_plan = await db.plans.find_one({"razorpay_plan_id": plan['id']})

            if not existing_plan:
                # If the plan does not exist, insert it into the database
                new_plan_data = {
                    'razorpay_plan_id': plan['id'],
                    'name': plan['item']['name'],
                    'amount': plan['item']['amount'] / 100,  # Convert paise to INR
                    'period': plan['period'],
                    'interval': plan['interval'],
                    'description': plan.get('description', ''),
                    'notes': plan['notes'],
                    'created_at': datetime.now(),
                }

                await db.plans.insert_one(new_plan_data)
                logger.info(f"Inserted new plan into the database: {plan['id']}")

            updated_plans.append(plan)

        # Return the updated list of plans
        return updated_plans

    except BadRequestError as e:
        logger.error(f"Error fetching plans: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error fetching plans: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred")



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

        # Prepare subscription data to save to the database
        subscription_data = {
            'subscription_id': subscription['id'],
            'user_id': str(current_user["_id"]),  # Convert ObjectId to string
            'plan_id': subscription_details.plan_id,
            'amount': total_amount,
            'customer_email': current_user["email"],
            'status': 'pending',  # Initial status set to pending
            'created_at': time.time(),
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
    



# 3. Handle payment webhook (Confirm payment and access services)# 3. Handle payment webhook (Confirm payment and access services)
@router.post("/webhook")
async def handle_webhook(request: Request):
    """
    Handles Razorpay payment webhooks to update subscription status automatically.
    """
    headers = request.headers
    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    webhook_signature = headers.get('X-Razorpay-Signature')

    if webhook_signature is None:
        raise HTTPException(status_code=400, detail="Missing Razorpay signature")

    webhook_body = await request.body()

    try:
        # Verify Razorpay webhook signature
        client.utility.verify_webhook_signature(webhook_body.decode('utf-8'), webhook_signature, webhook_secret)
    except SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    webhook_data = await request.json()
    event = webhook_data.get("event")
    logger.info(f"Received event: {event}")

    print(event)

    if event == "subscription.activated":
        # Subscription has been activated
        subscription_entity = webhook_data["payload"]["subscription"]["entity"]
        subscription_id = subscription_entity["id"]
        logger.info(f"Subscription {subscription_id} activated")

        # Update subscription status in MongoDB
        await update_subscription_status(subscription_id, status="active")

    elif event == "subscription.completed":
        # Subscription has been completed
        subscription_entity = webhook_data["payload"]["subscription"]["entity"]
        subscription_id = subscription_entity["id"]
        logger.info(f"Subscription {subscription_id} completed")

        # Update subscription status in MongoDB
        await update_subscription_status(subscription_id, status="completed")

    elif event == "subscription.halted":
        # Subscription has been halted due to issues (e.g., payment failure)
        subscription_entity = webhook_data["payload"]["subscription"]["entity"]
        subscription_id = subscription_entity["id"]
        logger.info(f"Subscription {subscription_id} halted")

        # Update subscription status in MongoDB
        await update_subscription_status(subscription_id, status="halted")

    elif event == "payment.failed":
        # Handle failed payment
        payment_entity = webhook_data["payload"]["payment"]["entity"]
        subscription_id = payment_entity.get("subscription_id")
        logger.info(f"Payment failed for subscription {subscription_id}")

        if subscription_id:
            # Update subscription status in MongoDB
            await update_subscription_status(subscription_id, status="payment_failed")

    else:
        logger.warning(f"Unhandled event: {event}")

    return {"status": "ok"}

async def update_subscription_status(subscription_id: str, status: str):
    """
    Helper function to update the subscription status in MongoDB.
    """
    try:
        # Fetch the subscription from MongoDB
        subscription = await db.subscriptions.find_one({'subscription_id': subscription_id})

        if not subscription:
            logger.error(f"Subscription not found for subscription_id: {subscription_id}")
            return

        # Update the subscription status in MongoDB
        result = await db.subscriptions.update_one(
            {"subscription_id": subscription_id},
            {"$set": {"status": status, "updated_at": time.time()}}
        )

        if result.modified_count > 0:
            logger.info(f"Subscription {subscription_id} status updated to {status}")
        else:
            logger.error(f"Failed to update subscription {subscription_id} status to {status}")
    except Exception as e:
        logger.error(f"Error updating subscription status: {str(e)}")



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





################################################################################################

#CANCEL SUBSCRIPTION

# Pydantic model to accept the necessary input
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






#########################################################################################################################


##INVOICE


# Pydantic model to define the invoice creation request
class InvoiceCreateRequest(BaseModel):
    subscription_id: str

# Pydantic model to define the response
class InvoiceResponse(BaseModel):
    invoice_id: str
    subscription_id: str
    user_details: dict
    service_details: dict
    invoice_details: dict

# Route to create an invoice for a subscription using only the subscription_id
@router.post("/create-invoice", response_model=InvoiceResponse)
async def create_invoice_for_subscription(
    invoice_data: InvoiceCreateRequest,
    current_user: User = Depends(get_current_user)
):
    
    current_user = User(**current_user)
    """
    Creates an invoice for a given subscription using the current logged-in user details.
    """
    try:
        # Fetch subscription details from Razorpay
        subscription = client.subscription.fetch(invoice_data.subscription_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")

        # Use the current user's details as the customer
        customer_details = {
            "email": current_user.email,
            "name": current_user.name,
            "contact": current_user.phone_no
        }
        
        # Fetch plan details from Razorpay using the plan_id from the subscription
        plan_id = subscription['plan_id']
        plan = client.plan.fetch(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        # Create the invoice in Razorpay using current user's details (without due_date)
        invoice_payload = {
            "type": "invoice",
            "customer": {
                "email": customer_details["email"],
                "name": customer_details["name"],
                "contact": customer_details["contact"]
            },
            "line_items": [
                {
                    "name": plan["item"]["name"],
                    "amount": plan["item"]["amount"],  # Razorpay stores amount in paise
                    "currency": "INR",
                    "quantity": 1,
                    "description": plan["item"].get("description", "")
                }
            ],
            "subscription_id": invoice_data.subscription_id,
            "currency": "INR",
            "description": f"Invoice for plan {plan['item']['name']}",
            "notes": {
                "created_by": current_user.email
            }
        }

        # Send request to Razorpay to create the invoice
        invoice = client.invoice.create(invoice_payload)

        # Prepare the response data
        response_data = {
            "invoice_id": invoice["id"],
            "subscription_id": invoice_data.subscription_id,
            "user_details": {
                "name": customer_details["name"],
                "email": customer_details["email"],
                "contact": customer_details["contact"]
            },
            "service_details": {
                "plan_name": plan["item"]["name"],
                "amount": plan["item"]["amount"] / 100,  # Convert paise to INR
                "period": plan["period"],
                "interval": plan["interval"],
                "description": plan["item"].get("description", "")
            },
            "invoice_details": {
                "amount_due": invoice["amount_due"] / 100,  # Convert paise to INR
                "status": invoice["status"],
                "currency": invoice["currency"],
                "invoice_url": invoice.get("short_url")
            }
        }

        return response_data

    except BadRequestError as e:
        logger.error(f"Error creating invoice: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error creating invoice: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while creating the invoice")
