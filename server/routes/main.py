# main.py - Simple FastAPI server
from fastapi import FastAPI

app = FastAPI()

@app.get("/login")
async def login():
	
	return {}

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from routes.schema import User, SessionLocal

class LoginRequest(BaseModel):
	username: str
	password: str

def get_db():
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()


@app.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
	user = db.query(User).filter(User.username == request.username).first()
	if user and user.password == request.password:
		return {"success": True, "message": "Login successful", "type": user.type.value}
	raise HTTPException(status_code=401, detail="Invalid username or password")

# Create admin endpoint
class CreateAdminRequest(BaseModel):
	username: str
	password: str

@app.post("/create-admin")
def create_admin(request: CreateAdminRequest, db: Session = Depends(get_db)):
	from routes.schema import UserType
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
	return {"success": True, "message": "Admin user created", "id": new_admin.id}

