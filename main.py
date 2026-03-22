from fastapi import FastAPI, HTTPException
import boto3
from botocore.exceptions import ClientError
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from uuid import uuid4
from datetime import datetime

# Load environment variables
load_dotenv()

# Initialize FastAPI app ONCE
app = FastAPI()

# Configure CORS ONCE (before adding to middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load AWS credentials from environment
AWS_REGION = os.getenv("AWS_REGION")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
RIDERS_TABLE_NAME = os.getenv("DYNAMO_TABLE_NAME")
PORTAL_USERS_TABLE_NAME = os.getenv("PORTAL_USERS_TABLE_NAME", "PortalUsers")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")  # Add this to your .env

# Initialize DynamoDB
dynamodb = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)
riders_table = dynamodb.Table(RIDERS_TABLE_NAME)
portal_users_table = dynamodb.Table(PORTAL_USERS_TABLE_NAME)

# Initialize S3 client
s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)

# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────

class UserUpdate(BaseModel):
    FirstName: str
    LastName: str
    Email: str
    MobileNumber: str
    MaritalStatus: str
    DateOfBirth: str


class RiderCreate(BaseModel):
    FirstName: str
    LastName: str
    Email: str
    MobileNumber: str
    Gender: str
    DateOfBirth: str
    MaritalStatus: str
    KYCRequired: str
    # Document S3 URLs (optional — uploaded separately via pre-signed URLs)
    AadhaarFrontUrl: Optional[str] = None
    AadhaarBackUrl: Optional[str] = None
    PanFrontUrl: Optional[str] = None
    PanBackUrl: Optional[str] = None
    LicenseFrontUrl: Optional[str] = None
    LicenseBackUrl: Optional[str] = None


# ─────────────────────────────────────────────
# Existing Endpoints
# ─────────────────────────────────────────────

@app.get("/riders")
def get_riders():
    try:
        response = riders_table.scan()
        data = response.get("Items", [])
        return {"riders": data}
    except Exception as e:
        return {"error": str(e), "riders": []}


@app.get("/portal-users")
def get_portal_users():
    try:
        response = portal_users_table.scan()
        data = response.get("Items", [])
        return {"users": data}
    except Exception as e:
        return {"error": str(e), "users": []}


@app.put("/portal-users/{user_id}")
def update_portal_user(user_id: int, user_data: UserUpdate):
    try:
        portal_users_table.update_item(
            Key={"UserID": int(user_id)},
            UpdateExpression="SET FirstName = :fn, LastName = :ln, Email = :em, MobileNumber = :mn, MaritalStatus = :ms, DateOfBirth = :dob",
            ExpressionAttributeValues={
                ":fn": user_data.FirstName,
                ":ln": user_data.LastName,
                ":em": user_data.Email,
                ":mn": user_data.MobileNumber,
                ":ms": user_data.MaritalStatus,
                ":dob": user_data.DateOfBirth,
            },
            ReturnValues="ALL_NEW"
        )
        return {"message": "User updated successfully", "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ─────────────────────────────────────────────
# New Endpoint 1: Generate Pre-Signed S3 Upload URL
# ─────────────────────────────────────────────

@app.get("/generate-upload-url")
def generate_upload_url(file_name: str, content_type: str, rider_id: str):
    """
    Generates a pre-signed S3 URL so the frontend can upload
    an image directly to S3 without exposing AWS credentials.
    Returns both the upload URL and the final S3 object URL.
    """
    try:
        # Build a unique S3 key: kyc/<rider_id>/<uuid>_<filename>
        unique_key = f"kyc/{rider_id}/{uuid4()}_{file_name}"

        upload_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": S3_BUCKET_NAME,
                "Key": unique_key,
                "ContentType": content_type,
            },
            ExpiresIn=300,  # URL expires in 5 minutes
        )

        # The permanent S3 URL for storing in DynamoDB
        s3_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{unique_key}"

        return {
            "upload_url": upload_url,
            "s3_url": s3_url,
        }

    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate upload URL: {str(e)}")


# ─────────────────────────────────────────────
# New Endpoint 2: Create Rider in DynamoDB
# ─────────────────────────────────────────────

@app.post("/riders")
def create_rider(rider: RiderCreate):
    """
    Saves a new rider record into the DynamoDB Riders table.
    The S3 document URLs are passed in from the frontend
    after it has already uploaded the files to S3.
    """
    try:
        # Generate a unique numeric RiderId using current timestamp in ms
        rider_id = int(datetime.utcnow().timestamp() * 1000)

        item = {
            "RiderId": rider_id,
            "FirstName": rider.FirstName,
            "LastName": rider.LastName,
            "Email": rider.Email,
            "MobileNumber": rider.MobileNumber,
            "Gender": rider.Gender,
            "DateOfBirth": rider.DateOfBirth,
            "MaritalStatus": rider.MaritalStatus,
            "KYCRequired": rider.KYCRequired,
            "KYCUploadedDateTime": datetime.utcnow().isoformat(),
            # Document URLs — stored as individual fields
            "AadhaarFrontUrl": rider.AadhaarFrontUrl or "",
            "AadhaarBackUrl": rider.AadhaarBackUrl or "",
            "PanFrontUrl": rider.PanFrontUrl or "",
            "PanBackUrl": rider.PanBackUrl or "",
            "LicenseFrontUrl": rider.LicenseFrontUrl or "",
            "LicenseBackUrl": rider.LicenseBackUrl or "",
            # Default statuses
            "DepositStatus": "Due",
            "RentalStatus": "Due",
            "ReasonforRejection": "",
            "DateofRejection": "",
            "ReUploadedStatus": "",
            "KYCVerifiedDateTime": "",
        }

        riders_table.put_item(Item=item)

        return {
            "message": "Rider created successfully",
            "success": True,
            "RiderId": rider_id,
        }

    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to create rider: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))