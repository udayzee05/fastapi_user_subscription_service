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
    prefix="/plans",
    tags=["Subscriptions"],
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


class PlanResponse(BaseModel):
    id: str
    period: str
    interval: int
    item: dict
    notes: dict

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
