from fastapi import FastAPI
import boto3
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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

# Initialize DynamoDB
dynamodb = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)
riders_table = dynamodb.Table(RIDERS_TABLE_NAME)
portal_users_table = dynamodb.Table(PORTAL_USERS_TABLE_NAME)

# Pydantic models for request validation
class UserUpdate(BaseModel):
    FirstName: str
    LastName: str
    Email: str
    MobileNumber: str
    MaritalStatus: str
    DateOfBirth: str

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