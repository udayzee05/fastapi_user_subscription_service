import motor.motor_asyncio
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId
from typing import Any, Optional
from pydantic_core import core_schema, CoreSchema
from pydantic.json_schema import GetJsonSchemaHandler, JsonSchemaValue
from pydantic import GetCoreSchemaHandler
import os
from datetime import datetime

from api.config import settings

# connect to mongodb
client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGODB_URL)

# create the news_summary_users database
db = client[settings.DB_NAME]

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

class BlogContentBase(BaseModel):
    title: str
    body: str

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Sample Blog Title",
                "body": "This is the content of the sample blog."
            }
        }

class BlogContentCreate(BlogContentBase):
    pass

class BlogContent(BlogContentBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class BlogContentResponse(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    title: str
    body: str
    auther_name: str
    auther_id: str
    created_at: str

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "title": "blog title",
                "body": "blog content",
                "auther_name": "name of the auther",
                "auther_id": "ID of the auther",
                "created_at": "Date of blog creation"
            }
        }

class User(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str
    email: EmailStr
    password: str
    role: str =Field(default="user")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "jdoe@example.com",
                "password": "secret_code",
                "role": "user"
            }
        }

class UserResponse(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str
    email: EmailStr
    role: str = Field(default="user")


    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "jdoe@example.com",
                "role": "user"
            }
        }


class ObjectCount(BaseModel):
    object_count: int
    timestamp: datetime
    original_image_url: str   # s3 url
    processed_image_url: str  # s3 url
    user_id: PyObjectId       # User ID who is going to count

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
                    "user_id": "60d5ecb8f1e2f0a5a4d7b2f1"
                }
            }
        }


class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    id: Optional[str] = None

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordReset(BaseModel):
    password: str
