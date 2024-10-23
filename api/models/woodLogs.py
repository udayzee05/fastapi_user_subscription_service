from pydantic import BaseModel, Field
from bson import ObjectId
from typing import Any
from pydantic_core import core_schema, CoreSchema
from pydantic import GetCoreSchemaHandler
from pydantic.json_schema import GetJsonSchemaHandler, JsonSchemaValue
from datetime import datetime

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


class ObjectCount(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    object_count: int
    timestamp: datetime
    original_image_url: str   # s3 url
    processed_image_url: str  # s3 url
    category: str
    user_id: PyObjectId   # User ID who is going to count

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "object_count": 0,
                "timestamp": "2022-01-01T00:00:00Z",
                "original_image_url": "https://example.com/original.png",
                "processed_image_url": "https://example.com/processed.png",
                "category": "service type",
                "user_id": "60d5ecb8f1e2f0a5a4d7b2f1"
            }
        }

class ObjectCountResponse(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    object_count: ObjectCount

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "_id": "60d5ecb8f1e2f0a5a4d7b2f1",
                "object_count": {
                    "object_count": 0,
                    "timestamp": "2022-01-01T00:00:00Z",
                    "original_image_url": "https://example.com/original.png",
                    "processed_image_url": "https://example.com/processed.png",
                    "category": "service type",

                    "user_id": "60d5ecb8f1e2f0a5a4d7b2f1"
                }
            }
        }

class CountRequest(BaseModel):
    base64_image: str
