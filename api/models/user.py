from pydantic import BaseModel, Field, EmailStr,field_validator,ValidationInfo
from bson import ObjectId
from typing import Any, Optional,List,Dict,Set
from pydantic_core import core_schema, CoreSchema
from pydantic.json_schema import GetJsonSchemaHandler, JsonSchemaValue
from pydantic import GetCoreSchemaHandler
import re
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


class User(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str
    email: EmailStr
    password: str
    phone_no: Optional[str] = None
    role: str =Field(default="user")
    trial_start_date: Optional[datetime] = None
    trial_end_date: Optional[datetime] = None
    subscribed_services:Set[str] = Field(default_factory=set)
     # New fields for user profile
    company_email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    gstin_number: Optional[str] = None
    profile_picture: Optional[str] = None 
    count_data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of dictionaries storing category, total images counted, and total object count"
    )

    @field_validator('password')
    @classmethod
    def password_validation(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[\W_]', v):
            raise ValueError('Password must contain at least one special character')
        return v
    @field_validator('phone_no')
    @classmethod
    def phone_number_validation(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        if v is not None:
            # Example rule: phone number must be 10 digits long and contain only digits
            if not re.fullmatch(r'\d{10}', v):
                raise ValueError('Phone number must be exactly 10 digits long')
        return v

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "jdoe@example.com",
                "password": "secret_code",
                "phone_no": "9999999999",
                "role": "user"
            }
        }

class UserResponse(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    name: str
    email: EmailStr
    phone_no: Optional[str] = None
    role: str = Field(default="user")
    


    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "jdoe@example.com",
                "password": "secret_code",
                "phone_no": "9999999999",
                "role": "user"
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




class UserProfileUpdate(BaseModel):
    company_email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    gstin_number: Optional[str] = None
    profile_picture: Optional[str] = None  # URL to the profile picture

    @field_validator('gstin_number')
    def validate_gstin(cls, v):
        # GSTIN number must be exactly 15 characters long
        if v and len(v) != 15:
            raise ValueError('GSTIN must be exactly 15 characters long')

        # GSTIN number format: First 2 digits, next 10 characters (PAN), digit, alphabet, digit/alphabet
        gstin_pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1}$'

        if not re.match(gstin_pattern, v):
            raise ValueError('Invalid GSTIN format')

        return v


class UserProfileResponse(BaseModel):
    role: str
    email: EmailStr
    company_email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    gstin_number: Optional[str] = None
    profile_picture: Optional[str] = None  # URL to the profile picture