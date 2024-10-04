import logging
from fastapi import HTTPException,APIRouter, Request
import razorpay
from razorpay.errors import  SignatureVerificationError
from schemas import  db
from config import settings
import time
router = APIRouter(
    prefix="/webhook",
    tags=["Subscriptions"],
)

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Razorpay client
client = razorpay.Client(auth=(settings.TEST_RAZORPAY_API_KEY, settings.TEST_RAZORPAY_SECRET_KEY))

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



