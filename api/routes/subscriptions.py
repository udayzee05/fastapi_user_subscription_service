import logging
from fastapi import FastAPI, HTTPException, Depends, APIRouter, Request, Query, Form
import razorpay
from datetime import datetime, timedelta
from ..schemas import db, Subscription, User
from ..oauth2 import get_current_user
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from api.config import settings

router = APIRouter(
    prefix="/subscriptions",
    tags=["Subscriptions"]
)

templates = Jinja2Templates(directory="api/templates")

# Razorpay client
client = razorpay.Client(auth=(settings.RAZORPAY_API_KEY, settings.RAZORPAY_SECRET_KEY))

@router.get("/payment", response_class=HTMLResponse)
async def payment_page(
    request: Request,
    user: dict = Depends(get_current_user),
    subscription_type: str = Query(..., regex="^(monthly|yearly)$"),
):
    user_model = User(**user)  # Convert the user dictionary to a Pydantic model

    # Check if the user is currently in a trial period
    if user_model.trial_end_date and user_model.trial_end_date > datetime.now():
        trial_remaining_days = (user_model.trial_end_date - datetime.now()).days
        return HTMLResponse(content=f"You are currently on a trial period. {trial_remaining_days} days remaining.", status_code=200)

    try:
        # Check for existing active subscription
        existing_subscription = await db.subscriptions.find_one({"user_id": str(user_model.id), "status": "active"})
        
        if existing_subscription:
            logging.info(f"Existing subscription found for user {user_model.email}: {existing_subscription}")
            # Extend the subscription
            if subscription_type == "monthly":
                additional_days = 30
                amount = 10000  # 100.00 INR in paise
            elif subscription_type == "yearly":
                additional_days = 365
                amount = 120000  # 1200.00 INR in paise
            else:
                raise HTTPException(status_code=400, detail="Invalid subscription type")
            
            # Calculate new end date
            new_end_date = existing_subscription["end_date"] + timedelta(days=additional_days)
            
            # Update subscription details
            updated_subscription = await db.subscriptions.update_one(
                {"_id": existing_subscription["_id"]},
                {"$set": {"end_date": new_end_date, "amount": existing_subscription["amount"] + amount}}
            )
            logging.info(f"Subscription extended for user {user_model.email}: {updated_subscription}")
            
            return HTMLResponse(content=f"Subscription extended until {new_end_date}", status_code=200)

        # If no existing subscription, create a new one
        if subscription_type == "monthly":
            amount = 10000  # 100.00 INR in paise
        elif subscription_type == "yearly":
            amount = 120000  # 1200.00 INR in paise
        else:
            raise HTTPException(status_code=400, detail="Invalid subscription type")

        order_data = {
            "amount": amount,  # Amount in paise
            "currency": "INR",
            "payment_capture": 1,
        }
        order = client.order.create(data=order_data)
        order_id = order["id"]

        # Convert user_id ObjectId to string
        user_id_str = str(user_model.id)

        # Create a subscription entry in the database with status 'pending'
        subscription = Subscription(
            user_id=user_id_str,
            order_id=order_id,
            subscription_type=subscription_type,
            amount=amount,
            status="pending"
        )
        await db.subscriptions.insert_one(subscription.dict(by_alias=True))
        logging.info(f"Subscription created: {subscription.dict(by_alias=True)}")

    except Exception as e:
        logging.error(f"Error in processing payment: {e}")
        return HTMLResponse(content=f"Error in processing payment: {e}", status_code=500)

    return templates.TemplateResponse(
        "payment.html",
        {
            "request": request,
            "email": user_model.email,
            "order_id": order_id,
            "subscription_type": subscription_type,
            "amount": amount,  # Pass the amount in paise
            "razorpay_key": settings.RAZORPAY_API_KEY,
        },
    )

@router.post("/payment/success")
async def payment_success(
    request: Request,
    razorpay_order_id: str = Form(...),
    razorpay_payment_id: str = Form(...),
    razorpay_signature: str = Form(...)
):
    logging.info(f"Payment success data: order_id={razorpay_order_id}, payment_id={razorpay_payment_id}, signature={razorpay_signature}")

    try:
        # Verify the payment signature
        client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })
    except razorpay.errors.SignatureVerificationError:
        logging.error("Invalid payment signature")
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # You can add additional logic to update the subscription status or any other business logic here
    return JSONResponse(content={"status": "success"}, status_code=200)

@router.post("/webhook")
async def handle_webhook(request: Request):
    headers = request.headers
    logging.info(f"Request headers: {headers}")

    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    webhook_signature = request.headers.get('X-Razorpay-Signature')
    user_agent = request.headers.get('User-Agent')

    if webhook_signature is None:
        if 'Razorpay-Webhook' not in user_agent:
            logging.error("Missing X-Razorpay-Signature header or invalid User-Agent")
            raise HTTPException(status_code=400, detail="This endpoint is for Razorpay webhooks only.")
        else:
            logging.error("Missing X-Razorpay-Signature header")
            raise HTTPException(status_code=400, detail="Missing X-Razorpay-Signature header")

    webhook_body = await request.body()
    logging.info(f"Request body: {webhook_body.decode('utf-8')}")

    try:
        # Convert the webhook_body to a string
        webhook_body_str = webhook_body.decode('utf-8')

        # Verify webhook signature
        client.utility.verify_webhook_signature(
            webhook_body_str, webhook_signature, webhook_secret
        )
    except razorpay.errors.SignatureVerificationError:
        logging.error("Invalid webhook signature")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    webhook_data = await request.json()
    event = webhook_data.get("event")
    logging.info(f"Received event: {event}")

    if event == "payment.captured":
        payment_id = webhook_data["payload"]["payment"]["entity"]["id"]
        order_id = webhook_data["payload"]["payment"]["entity"]["order_id"]
        amount = webhook_data["payload"]["payment"]["entity"]["amount"]
        
        # Update the subscription status in the database
        await update_subscription_status(order_id, payment_id, amount)
        return JSONResponse(content={"status": "success"}, status_code=200)

    # Log other events
    logging.info(f"Unhandled event type: {event}")

    # Respond appropriately for unhandled events
    return JSONResponse(content={"status": f"event {event} not handled"}, status_code=200)

async def update_subscription_status(order_id: str, payment_id: str, amount: int):
    logging.info(f"Updating subscription for order_id: {order_id}, payment_id: {payment_id}, amount: {amount}")
    # Find the subscription by order_id
    subscription = await db.subscriptions.find_one({"order_id": order_id})
    if subscription:
        logging.info(f"Subscription found: {subscription}")
        # Update subscription status and payment details
        subscription["status"] = "active"
        subscription["payment_id"] = payment_id
        subscription["amount"] = amount
        subscription["start_date"] = datetime.now()
        subscription["end_date"] = datetime.now() + timedelta(days=30 if subscription["subscription_type"] == "monthly" else 365)
        await db.subscriptions.replace_one({"order_id": order_id}, subscription)
        logging.info(f"Subscription updated: {subscription}")
    else:
        logging.error(f"Subscription not found for order_id: {order_id}")
        raise HTTPException(status_code=404, detail="Subscription not found")

