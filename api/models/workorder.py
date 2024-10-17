from pydantic import BaseModel, Field
from bson import ObjectId
from typing import Any
from pydantic_core import core_schema, CoreSchema
from pydantic import GetCoreSchemaHandler
from pydantic.json_schema import GetJsonSchemaHandler, JsonSchemaValue
from datetime import datetime
import uuid


class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        def validate(value: str) -> ObjectId:
            if not ObjectId.is_valid(value):
                raise ValueError("Invalid ObjectId")
            return ObjectId(value)
        return core_schema.no_info_plain_validator_function(
            function=validate,
            serialization=core_schema.to_string_ser_schema()
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return handler(core_schema.str_schema())

# Pydantic model for the WorkOrder
class WorkOrder(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    work_order_id: str = Field(default_factory=lambda: f"WO-{uuid.uuid4().hex[:8]}")
    user_id: PyObjectId   # The ID of the user creating the work order
    service_type: str     # Service type (e.g., 'API 5L X52', 'mildSteelBars')
    number_of_orders: int
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {ObjectId: str}

# Model for creating a new work order
class WorkOrderCreateRequest(BaseModel):
    service_type: str
    number_of_orders: int

# Model for retrieving work order details
class WorkOrderResponse(BaseModel):
    work_order_id: str
    service_type: str
    number_of_orders: int
    created_at: datetime