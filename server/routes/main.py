# main.py - Simple FastAPI server
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session
from routes.schema import User, SessionLocal, UserType
from routes.middleware import create_access_token, verify_token
import jwt
from datetime import timedelta

app = FastAPI()
security = HTTPBearer()

# JWT configuration (should match middleware.py)
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 720  # 12 hours

# python -m uvicorn routes.main:app --reload
# cd /Users/adityasahrawat/dev/projects/Aerothon/server
# source .venv/bin/activate


class LoginRequest(BaseModel):
	username: str
	password: str


class CreateUserRequest(BaseModel):
	username: str
	password: str
	usertype: UserType


class CreateAdminRequest(BaseModel):
	username: str
	password: str


class ChangePasswordRequest(BaseModel):
	old_password: str
	new_password: str


def get_db():
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()

@app.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
	"""Login endpoint that returns a JWT token"""
	user = db.query(User).filter(User.username == request.username).first()
	if user and user.password == request.password:
		# Create access token
		access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
		access_token = create_access_token(
			data={"sub": user.username}, expires_delta=access_token_expires
		)
		return {
			"success": True,
			"message": "Login successful",
			"access_token": access_token,
			"token_type": "bearer",
			"user_type": user.type.value,
			"user_id": user.user_id
		}
	raise HTTPException(status_code=401, detail="Invalid username or password")

# Create admin endpoint
class CreateAdminRequest(BaseModel):
	username: str
	password: str

@app.post("/create-admin")
def create_admin(request: CreateAdminRequest, db: Session = Depends(get_db)):
	"""Create an admin user (initial setup only)"""
	# Check if username already exists
	existing = db.query(User).filter(User.username == request.username).first()
	if existing:
		raise HTTPException(status_code=400, detail="Username already exists")
	new_admin = User(
		username=request.username,
		password=request.password,
		type=UserType.admin
	)
	db.add(new_admin)
	db.commit()
	db.refresh(new_admin)
	return {
		"success": True,
		"message": "Admin user created",
		"user_id": new_admin.user_id,
		"username": new_admin.username
	}


@app.post("/create-user")
def create_user(
	request: CreateUserRequest,
	credentials = Depends(security),
	db: Session = Depends(get_db)
):
	"""Create a new user. Only admins can create users."""
	# Verify JWT token and get user
	try:
		payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
		username: str = payload.get("sub")
		if username is None:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="Invalid authentication credentials"
			)
	except jwt.InvalidTokenError:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid or expired token"
		)
	
	# Check if requesting user exists and is admin
	author = db.query(User).filter(User.username == username).first()
	if not author:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found"
		)
	if author.type != UserType.admin:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Only admins can create users"
		)
	
	# Check if new username already exists
	existing = db.query(User).filter(User.username == request.username).first()
	if existing:
		raise HTTPException(status_code=400, detail="Username already exists")
	
	# Create new user
	new_user = User(
		username=request.username,
		password=request.password,
		type=request.usertype
	)
	db.add(new_user)
	db.commit()
	db.refresh(new_user)
	return {
		"success": True,
		"message": f"{request.usertype.value} user created",
		"user_id": new_user.user_id,
		"username": new_user.username,
		"usertype": new_user.type.value
	}


@app.post("/change-password")
def change_password(
	request: ChangePasswordRequest,
	credentials = Depends(security),
	db: Session = Depends(get_db)
):
	"""Change user password. Requires JWT authentication."""
	# Verify JWT token and get user
	try:
		payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
		username: str = payload.get("sub")
		if username is None:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="Invalid authentication credentials"
			)
	except jwt.InvalidTokenError:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid or expired token"
		)
	
	# Get user from database
	user = db.query(User).filter(User.username == username).first()
	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found"
		)
	
	# Verify old password
	if user.password != request.old_password:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Old password is incorrect"
		)
	
	# Update password
	user.password = request.new_password
	db.commit()
	
	return {
		"success": True,
		"message": "Password changed successfully",
		"username": user.username
	}
