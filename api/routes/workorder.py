from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Any
from bson import ObjectId
from datetime import datetime
import uuid
from api.core.db import db
from api.core.oauth2 import get_current_user
from pydantic_core import core_schema, CoreSchema
from pydantic import GetCoreSchemaHandler
from pydantic.json_schema import GetJsonSchemaHandler, JsonSchemaValue

router = APIRouter(prefix="/workorder", tags=["WorkOrder"])

work_orders_collection = db["work_orders"]

class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        def validate(value: str) -> ObjectId:
            if not ObjectId.is_valid(value):
                raise ValueError("Invalid ObjectId")
            return ObjectId(value)

        return core_schema.no_info_plain_validator_function(
            function=validate,
            serialization=core_schema.to_string_ser_schema(),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return handler(core_schema.str_schema())

# Pydantic model for an individual order inside the WorkOrder
from typing import Union
class ObjectCountDetails(BaseModel):
    _id: PyObjectId
    object_count: int
    timestamp: datetime
    original_image_url: Optional[str] = None
    processed_image_url: Optional[str] = None
    category: Optional[str] = None

class Order(BaseModel):
    specification: Optional[str] = None
    grade: Optional[str] = None
    size_in_inches: Optional[float] = None
    length_in_m: Optional[float] = None
    qty_ordered: Optional[int] = None
    object_count_id: Optional[PyObjectId] = None
    object_count_details: Optional[ObjectCountDetails] = None  # Populated object

class WorkOrderResponse(BaseModel):
    work_order_id: str
    customer_name: Optional[str] = None
    customer_number: Optional[int] = None
    number_of_orders: Optional[int] = None
    orders: Optional[List[Order]] = None
    created_at: Optional[datetime] = None

    class Config:
        json_encoders = {ObjectId: str}


# Pydantic model for the WorkOrder
class WorkOrder(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    work_order_id: str = Field(default_factory=lambda: f"WO-{uuid.uuid4().hex[:8]}")
    user_id: PyObjectId
    customer_name: Optional[str] = None  # Can be null or optional
    customer_number: Optional[int] = None
    number_of_orders: Optional[int] = None
    orders: Optional[List[Order]] = []  # Orders can be an empty list or None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {ObjectId: str}

# Model for creating a new work order
class WorkOrderCreateRequest(BaseModel):
    customer_name: Optional[str] = None
    customer_number: Optional[int] = None
    number_of_orders: Optional[int] = None

# Model for adding an order to a work order
class AddOrderRequest(BaseModel):
    specification: Optional[str] = None
    grade: Optional[str] = None
    size_in_inches: Optional[float] = None
    length_in_m: Optional[float] = None

# Pydantic model for the WorkOrder
class WorkOrder(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    work_order_id: str = Field(default_factory=lambda: f"WO-{uuid.uuid4().hex[:8]}")
    user_id: PyObjectId   # The ID of the user creating the work order
    customer_name: str
    customer_number: int
    number_of_orders: int
    orders: List[Order] = []  # List of orders
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {ObjectId: str}

# Model for creating a new work order
class WorkOrderCreateRequest(BaseModel):
    customer_name: str
    customer_number: int
    number_of_orders: int

# Model for adding an order to a work order (without qty_ordered for now)
class AddOrderRequest(BaseModel):
    specification: str
    grade: str
    size_in_inches: float
    length_in_m: float



# Create a new work order
@router.post("/", response_model=WorkOrderResponse)
async def create_work_order(
    work_order: WorkOrderCreateRequest,
    user: dict = Depends(get_current_user)
):
    """
    Endpoint to create a new work order.
    """
    new_work_order = WorkOrder(
        user_id=user["_id"],
        customer_name=work_order.customer_name,
        customer_number=work_order.customer_number,
        number_of_orders=work_order.number_of_orders
    )

    # Insert work order into the database
    inserted_work_order = await work_orders_collection.insert_one(new_work_order.dict(by_alias=True))

    if not inserted_work_order:
        raise HTTPException(status_code=500, detail="Failed to create work order")

    return WorkOrderResponse(
        work_order_id=new_work_order.work_order_id,
        customer_name=new_work_order.customer_name,
        customer_number=new_work_order.customer_number,
        number_of_orders=new_work_order.number_of_orders,
        orders=new_work_order.orders,
        created_at=new_work_order.created_at
    )

# Add an order to an existing work order (without qty_ordered initially)
@router.post("/{work_order_id}/add-order", response_model=WorkOrderResponse)
async def add_order_to_work_order(
    work_order_id: str,
    order: AddOrderRequest,
    user: dict = Depends(get_current_user)
):
    """
    Endpoint to add an order to an existing work order.
    """
    # Find the work order by ID and user
    work_order = await work_orders_collection.find_one({"work_order_id": work_order_id, "user_id": ObjectId(user["_id"])})

    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    # Create the new order object without qty_ordered
    new_order = Order(
        specification=order.specification,
        grade=order.grade,
        size_in_inches=order.size_in_inches,
        length_in_m=order.length_in_m
    )

    # Update the work order by adding the new order to the list of orders
    updated_result = await work_orders_collection.update_one(
        {"work_order_id": work_order_id, "user_id": ObjectId(user["_id"])},
        {"$push": {"orders": new_order.dict()}}
    )

    if updated_result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to add order to the work order")

    # Retrieve the updated work order
    updated_work_order = await work_orders_collection.find_one({"work_order_id": work_order_id, "user_id": ObjectId(user["_id"])})

    return WorkOrderResponse(
        work_order_id=updated_work_order["work_order_id"],
        customer_name=updated_work_order["customer_name"],
        customer_number=updated_work_order["customer_number"],
        number_of_orders=updated_work_order["number_of_orders"],
        orders=updated_work_order["orders"],
        created_at=updated_work_order["created_at"]
    )
@router.get("/", response_model=List[WorkOrderResponse])
async def get_all_work_orders_for_user(
    user: dict = Depends(get_current_user)
):
    """
    Endpoint to retrieve all work orders for the current user.
    """
    work_orders = await work_orders_collection.find(
        {"user_id": ObjectId(user["_id"])}
    ).to_list(length=100)

    return [
        WorkOrderResponse(
            work_order_id=wo["work_order_id"],
            customer_name=wo.get("customer_name"),
            customer_number=wo.get("customer_number"),
            number_of_orders=wo.get("number_of_orders", 0),
            orders=wo.get("orders", []),
            created_at=wo["created_at"]
        ) for wo in work_orders
    ]



@router.get("/{work_order_id}/orders", response_model=List[Order])
async def get_all_orders_from_work_order(
    work_order_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Endpoint to retrieve all orders from a specific work order.
    """
    work_order = await work_orders_collection.find_one(
        {"work_order_id": work_order_id, "user_id": ObjectId(user["_id"])}
    )

    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    return work_order.get("orders", [])

@router.get("/work_order/{work_order_id}", response_model=WorkOrderResponse)
async def get_work_order_with_counts(
    work_order_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Get a work order with populated object counts for each order.
    """
    pipeline = [
        # Match the work order by ID and user
        {"$match": {"work_order_id": work_order_id, "user_id": ObjectId(user["_id"])}},

        # Unwind the orders array to process each order individually
        {"$unwind": "$orders"},

        # Use $lookup to join with the object_counts collection using object_count_id
        {
            "$lookup": {
                "from": "object_counts",  
                "localField": "orders.object_count_id",  
                "foreignField": "_id",  
                "as": "orders.object_count_details"
            }
        },

        # Unwind the object_count_details array to flatten the structure
        {"$unwind": {"path": "$orders.object_count_details", "preserveNullAndEmptyArrays": True}},

        # Group the data back into the original structure
        {
            "$group": {
                "_id": "$_id",
                "work_order_id": {"$first": "$work_order_id"},
                "user_id": {"$first": "$user_id"},
                "customer_name": {"$first": "$customer_name"},
                "customer_number": {"$first": "$customer_number"},
                "number_of_orders": {"$first": "$number_of_orders"},
                "created_at": {"$first": "$created_at"},
                "orders": {"$push": "$orders"}
            }
        }
    ]

    # Execute the aggregation pipeline
    result = await work_orders_collection.aggregate(pipeline).to_list(length=1)

    if not result:
        raise HTTPException(status_code=404, detail="Work order not found")

    # Return the first result mapped to WorkOrderResponse
    return WorkOrderResponse(**result[0])
