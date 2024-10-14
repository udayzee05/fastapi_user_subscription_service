
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional


# P
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

class InvoiceCreateRequest(BaseModel):
    subscription_id: str

# Pydantic model to define the response
class InvoiceResponse(BaseModel):
    invoice_id: str
    subscription_id: str
    user_details: dict
    service_details: dict
    invoice_details: dict

class SubscriptionDetails(BaseModel):
    plan_id: str
    currency: str = 'INR'

    
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



class CancelSubscriptionRequest(BaseModel):
    subcription_id: str


class SubscriptionDetailResponse(BaseModel):
    subscription_id: str
    plan_name: str
    status: str
    start_date: Optional[datetime]  # Make start_date optional
    end_date: Optional[datetime]    # Make end_date optional
