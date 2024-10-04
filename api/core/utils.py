# library imports
# pip install "passlib[bcrypt]"
import logging
from passlib.context import CryptContext
from fastapi import Depends, HTTPException,status

from schemas import User,db
from core.oauth2 import get_current_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)



async def check_admin_user(user: dict = Depends(get_current_user)):
    if not isinstance(user, User):
        user = User(**user)
    if user.role != "admin":
        raise HTTPException(
            status_code=403, detail="Access forbidden: Requires admin role"
        )
    return user



# Dependency to check if the user has a valid subscription
async def check_valid_subscription(current_user: User = Depends(get_current_user)):
    """
    Dependency function to check if the user has an active or completed subscription.
    """
    try:
        # Fetch user's subscriptions from the database
        user_subscriptions = await db.subscriptions.find({"user_id": current_user["_id"]}).to_list(length=None)
        
        # Check if any subscription is active or completed
        valid_subscription = any(sub['status'] in ["active", "completed"] for sub in user_subscriptions)
        
        if not valid_subscription:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: No active or completed subscription found."
            )
        
        return True  # Return True if the user has a valid subscription
    
    except Exception as e:
        logger.error(f"Error while checking subscription: {str(e)}")
        raise HTTPException(status_code=500, detail="Error checking subscription status")





