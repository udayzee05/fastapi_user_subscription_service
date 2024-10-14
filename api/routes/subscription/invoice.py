import logging
from fastapi import HTTPException, Depends, APIRouter
import razorpay
from razorpay.errors import BadRequestError
from core.db import db
from core.razorpay import client
from models.user import User
from core.oauth2 import get_current_user
from config import settings
from models.subscriptions import InvoiceCreateRequest, InvoiceResponse
router = APIRouter(
    prefix="/invoice",
    tags=["Invoices"]
)

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)




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
