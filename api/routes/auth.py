from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from models.user import Token
from core.db import db
from core.oauth2 import create_access_token
from core.utils import verify_password
import logging
import logging
from fastapi import  HTTPException, Depends, APIRouter
import razorpay
from config import settings
router = APIRouter(
    prefix="/login",
    tags=["Authentication"]
)
client = razorpay.Client(auth=(settings.TEST_RAZORPAY_API_KEY, settings.TEST_RAZORPAY_SECRET_KEY))

# Assume this is the sync function that you already implemented
async def sync_subscriptions_for_user(user_id: str):
    """
    Syncs the user's subscription statuses from Razorpay and updates the local database.
    """
    try:
        # Fetch user's subscriptions from the database
        user_subscriptions = await db.subscriptions.find({"user_id": user_id}).to_list(length=None)

        if not user_subscriptions:
            return {"message": "No subscriptions found to sync."}

        # Loop through each subscription and sync the status with Razorpay
        for subscription in user_subscriptions:
            subscription_id = subscription.get("subscription_id")
            
            try:
                # Fetch the latest status from Razorpay
                razorpay_subscription = client.subscription.fetch(subscription_id)
                latest_status = razorpay_subscription['status']

                # If the status has changed, update it in the local database
                if latest_status != subscription['status']:
                    await db.subscriptions.update_one(
                        {"subscription_id": subscription_id},
                        {"$set": {"status": latest_status}}
                    )
                    logging.info(f"Updated subscription {subscription_id} status to {latest_status}")

            except Exception as e:
                logging.error(f"Error syncing subscription {subscription_id}: {str(e)}")

        return {"message": "Subscriptions synced successfully."}

    except Exception as e:
        logging.error(f"Error syncing subscriptions for user {user_id}: {str(e)}")
        return {"message": "Error syncing subscriptions."}


@router.post("", response_model=Token, status_code=status.HTTP_200_OK)
async def login(user_credentials: OAuth2PasswordRequestForm = Depends()):
    # Fetch the user from the database based on username or email
    user = await db["users"].find_one({
        "$or": [
            {"name": user_credentials.username},
            {"email": user_credentials.username}
        ]
    })

    # Verify the password
    if user and verify_password(user_credentials.password, user["password"]):
        # Create access token
        access_token = create_access_token(payload={
            "id": user["_id"],
        })

        # Sync the user's subscriptions with Razorpay
        await sync_subscriptions_for_user(user["_id"])

        # Return the access token
        return {"access_token": access_token, "token_type": "bearer"}

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid user credentials"
        )
