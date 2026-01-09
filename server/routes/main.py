# main.py - Simple FastAPI server
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Query
from fastapi.security import HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from routes.schema import (
	User,
	SessionLocal,
	UserType,
	ChatConversation,
	ConversationMode,
	ConversationListResponse,
	CreateConversationRequest,
	CreateConversationResponse,
	ConversationHistoryResponse,
	SendMessageRequest,
	SendMessageResponse,
)
from routes.middleware import create_access_token, verify_token
from models import data_ingestion_public, data_ingestion_secure, rag_chat, rag_chat_dual
from neo4j import GraphDatabase
import jwt
from datetime import datetime, timedelta
from typing import List, Optional

app = FastAPI()
security = HTTPBearer()

# Initialize Neo4j driver for ingestion routes
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

@app.on_event("startup")
async def startup():
    """Initialize Neo4j driver on app startup."""
    app.state.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        app.state.neo4j_driver.verify_connectivity()
        print("✅ Neo4j Connected")
    except Exception as e:
        print(f"❌ Neo4j Connection Failed: {e}")

@app.on_event("shutdown")
async def shutdown():
    """Close Neo4j driver on app shutdown."""
    if hasattr(app.state, "neo4j_driver"):
        app.state.neo4j_driver.close()

# Enable CORS for frontend
app.add_middleware(
	CORSMiddleware,
	allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# JWT configuration (should match middleware.py)
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 720  # 12 hours

# python -m uvicorn routes.main:app --reload --host 0.0.0.0 --port 8000
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


class ChatRequest(BaseModel):
	user_input: str
	session_id: str = "default_user"

 
def get_db():
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()


def get_current_user(
	credentials=Depends(security),
	db: Session = Depends(get_db),
) -> User:
	payload = verify_token(credentials.credentials)
	username: str | None = payload.get("sub")
	if not username:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
	user = db.query(User).filter(User.username == username).first()
	if not user:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
	return user


def require_roles(*allowed_roles: UserType):
	def _dep(current_user: User = Depends(get_current_user)) -> User:
		if current_user.type not in allowed_roles:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="Not authorized",
			)
		return current_user

	return _dep


def _allowed_conversation_modes_for(user: User) -> set[ConversationMode]:
	# Business rules from your spec:
	# - ruser: public only
	# - user/admin: dual only
	if user.type == UserType.ruser:
		return {ConversationMode.public}
	return {ConversationMode.dual}


def _neo_session_key(user: User, conversation_id: int) -> str:
	# Deterministic, per-user and per-conversation
	return f"u{user.user_id}_c{conversation_id}"

@app.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
	"""Login endpoint that returns a JWT token"""
	print(f"🔑 Login attempt for user: {request.username}")
	user = db.query(User).filter(User.username == request.username).first()
	if user and user.password == request.password:
		print(f"✅ Login successful for user: {request.username} (type: {user.type.value})")
		# Create access token
		access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
		access_token = create_access_token(
			data={"sub": user.username}, expires_delta=access_token_expires
		)
		print(f"🎫 JWT token generated for {request.username}")
		return {
			"success": True,
			"message": "Login successful",
			"access_token": access_token,
			"token_type": "bearer",
			"user_type": user.type.value,
			"user_id": user.user_id
		}
	print(f"❌ Login failed for user: {request.username}")
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


# ============ INGESTION ROUTES (PUBLIC) ============
@app.post("/ingest/public")
async def ingest_public(
	background_tasks: BackgroundTasks,
	current_user: User = Depends(require_roles(UserType.admin)),
	files: List[UploadFile] = File(...),
	category: str = Form("general")
):
	"""Upload documents to public knowledge base."""
	print(f"📤 PUBLIC INGESTION: Received {len(files)} file(s) | Category: {category}")
	results = []
	import os
	os.makedirs("uploads", exist_ok=True)
	for file in files:
		file_path = os.path.abspath(f"uploads/{file.filename}")
		print(f"💾 Saving to: {file_path}")
		with open(file_path, "wb") as buffer:
			import shutil
			shutil.copyfileobj(file.file, buffer)
		background_tasks.add_task(
			data_ingestion_public.process_document,
			app.state.neo4j_driver,
			file_path,
			file.filename,
			"public",
			category
		)
		print(f"✅ Queued: {file.filename} for public ingestion")
		results.append({"file": file.filename, "status": "queued"})
	print(f"📊 PUBLIC INGESTION: {len(results)} file(s) queued successfully")
	return {"message": "Files queued for ingestion", "results": results}


# ============ INGESTION ROUTES (SECURE) ============
@app.post("/ingest/secure")
async def ingest_secure(
	background_tasks: BackgroundTasks,
	current_user: User = Depends(require_roles(UserType.admin)),
	files: List[UploadFile] = File(...),
	category: str = Form("confidential")
):
	"""Upload documents to secure knowledge base."""
	print(f"🔒 SECURE INGESTION: Received {len(files)} file(s) | Category: {category}")
	results = []
	import os
	os.makedirs("secure_uploads", exist_ok=True)
	for file in files:
		file_path = os.path.abspath(f"secure_uploads/{file.filename}")
		print(f"💾 Saving to: {file_path}")
		with open(file_path, "wb") as buffer:
			import shutil
			shutil.copyfileobj(file.file, buffer)
		background_tasks.add_task(
			data_ingestion_secure.process_document,
			app.state.neo4j_driver,
			file_path,
			file.filename,
			"secure",
			category
		)
		print(f"✅ Queued: {file.filename} for secure ingestion")
		results.append({"file": file.filename, "status": "queued"})
	print(f"📊 SECURE INGESTION: {len(results)} file(s) queued successfully")
	return {"message": "Files queued for secure ingestion", "results": results}


# ============ CHAT ROUTES ============
@app.post("/chat")
async def chat(request: ChatRequest, current_user: User = Depends(require_roles(UserType.ruser))):
	"""Process RAG query with chat history (public DB only)."""
	session_id = f"legacy_public:{_neo_session_key(current_user, 0)}:{request.session_id}"
	print(f"💬 CHAT (PUBLIC): Session={session_id} | Query: {request.user_input[:50]}...")
	response = rag_chat.rag_chat(request.user_input, session_id)
	print(f"✅ CHAT (PUBLIC): Response generated with {len(response.get('sources', []))} source(s)")
	return response


@app.get("/chat/history/{session_id}")
async def get_chat_history(session_id: str, current_user: User = Depends(require_roles(UserType.ruser))):
	"""Retrieve chat history for public chat session."""
	safe_session_id = f"legacy_public:{_neo_session_key(current_user, 0)}:{session_id}"
	print(f"📜 Retrieving CHAT history for session: {safe_session_id}")
	try:
		from langchain_neo4j import Neo4jChatMessageHistory
		history = Neo4jChatMessageHistory(
			url=NEO4J_URI,
			username=NEO4J_USER,
			password=NEO4J_PASSWORD,
			session_id=safe_session_id
		)
		from langchain_core.messages import HumanMessage, AIMessage
		return {
			"session_id": session_id,
			"history": [
				{"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.content}
				for m in history.messages
			]
		}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))


# ============ DUAL CHAT ROUTES (PUBLIC + SECURE) ============
@app.post("/chat-dual")
async def chat_dual(request: ChatRequest, current_user: User = Depends(require_roles(UserType.admin, UserType.user))):
	"""Process RAG query with dual retrieval (public + secure DBs)."""
	session_id = f"legacy_dual:{_neo_session_key(current_user, 0)}:{request.session_id}"
	print(f"💬 CHAT-DUAL: Session={session_id} | Query: {request.user_input[:50]}...")
	response = rag_chat_dual.rag_chat_dual(request.user_input, session_id)
	print(f"✅ CHAT-DUAL: Response generated with {len(response.get('sources', []))} source(s)")
	return response


@app.get("/chat-dual/history/{session_id}")
async def get_chat_dual_history(session_id: str, current_user: User = Depends(require_roles(UserType.admin, UserType.user))):
	"""Retrieve chat history for dual-DB chat session."""
	safe_session_id = f"legacy_dual:{_neo_session_key(current_user, 0)}:{session_id}"
	print(f"📜 Retrieving CHAT-DUAL history for session: dual_{safe_session_id}")
	try:
		from langchain_neo4j import Neo4jChatMessageHistory
		# Use dual_ prefix to separate from single-DB history
		history = Neo4jChatMessageHistory(
			url=NEO4J_URI,
			username=NEO4J_USER,
			password=NEO4J_PASSWORD,
			session_id=f"dual_{safe_session_id}"
		)
		from langchain_core.messages import HumanMessage, AIMessage
		return {
			"session_id": session_id,
			"history": [
				{"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.content}
				for m in history.messages
			]
		}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))


# ============ CONVERSATION ROUTES (NEW) ============
@app.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
	mode: Optional[str] = Query(default=None),
	current_user: User = Depends(get_current_user),
	db: Session = Depends(get_db),
):
	allowed_modes = _allowed_conversation_modes_for(current_user)
	query = db.query(ChatConversation).filter(ChatConversation.user_id == current_user.user_id)

	if mode is not None:
		try:
			mode_enum = ConversationMode(mode)
		except ValueError:
			raise HTTPException(status_code=400, detail="Invalid mode")
		if mode_enum not in allowed_modes:
			raise HTTPException(status_code=403, detail="Not authorized for this mode")
		query = query.filter(ChatConversation.mode == mode_enum)
	else:
		query = query.filter(ChatConversation.mode.in_(list(allowed_modes)))

	rows = query.order_by(ChatConversation.updated_at.desc()).all()
	return {
		"items": [
			{
				"conversation_id": r.conversation_id,
				"mode": r.mode.value,
				"title": r.title,
				"created_at": r.created_at,
				"updated_at": r.updated_at,
			}
			for r in rows
		]
	}


@app.post("/conversations", response_model=CreateConversationResponse, status_code=201)
def create_conversation(
	request: CreateConversationRequest,
	current_user: User = Depends(get_current_user),
	db: Session = Depends(get_db),
):
	allowed_modes = _allowed_conversation_modes_for(current_user)

	mode_value = request.mode
	if mode_value is None:
		# Default to the only allowed mode
		mode_enum = next(iter(allowed_modes))
	else:
		try:
			mode_enum = ConversationMode(mode_value)
		except ValueError:
			raise HTTPException(status_code=400, detail="Invalid mode")
		if mode_enum not in allowed_modes:
			raise HTTPException(status_code=403, detail="Not authorized for this mode")

	row = ChatConversation(
		user_id=current_user.user_id,
		mode=mode_enum,
		title=request.title,
		created_at=datetime.now(),
		updated_at=datetime.now(),
	)
	db.add(row)
	db.commit()
	db.refresh(row)

	return {"conversation_id": row.conversation_id, "mode": row.mode.value, "title": row.title}


def _get_conversation_or_404(
	conversation_id: int,
	current_user: User,
	db: Session,
) -> ChatConversation:
	row = db.query(ChatConversation).filter(ChatConversation.conversation_id == conversation_id).first()
	if not row:
		raise HTTPException(status_code=404, detail="Conversation not found")
	if row.user_id != current_user.user_id:
		raise HTTPException(status_code=403, detail="Not authorized")
	allowed_modes = _allowed_conversation_modes_for(current_user)
	if row.mode not in allowed_modes:
		raise HTTPException(status_code=403, detail="Not authorized for this mode")
	return row


@app.get("/conversations/{conversation_id}/history", response_model=ConversationHistoryResponse)
def conversation_history(
	conversation_id: int,
	current_user: User = Depends(get_current_user),
	db: Session = Depends(get_db),
):
	conv = _get_conversation_or_404(conversation_id, current_user, db)
	session_key = _neo_session_key(current_user, conv.conversation_id)

	try:
		from langchain_neo4j import Neo4jChatMessageHistory
		from langchain_core.messages import HumanMessage

		neo_session_id = session_key
		if conv.mode == ConversationMode.dual:
			neo_session_id = f"dual_{session_key}"

		history = Neo4jChatMessageHistory(
			url=NEO4J_URI,
			username=NEO4J_USER,
			password=NEO4J_PASSWORD,
			session_id=neo_session_id,
		)
		return {
			"conversation_id": conv.conversation_id,
			"mode": conv.mode.value,
			"history": [
				{
					"role": "user" if isinstance(m, HumanMessage) else "assistant",
					"content": m.content,
				}
				for m in history.messages
			],
		}
	except Exception as e:
		raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversations/{conversation_id}/send", response_model=SendMessageResponse)
def conversation_send(
	conversation_id: int,
	request: SendMessageRequest,
	current_user: User = Depends(get_current_user),
	db: Session = Depends(get_db),
):
	conv = _get_conversation_or_404(conversation_id, current_user, db)
	session_key = _neo_session_key(current_user, conv.conversation_id)

	if conv.mode == ConversationMode.public:
		response = rag_chat.rag_chat(request.user_input, session_key)
	else:
		response = rag_chat_dual.rag_chat_dual(request.user_input, session_key)

	# Maintain list metadata
	conv.updated_at = datetime.now()
	if not conv.title:
		conv.title = (request.user_input or "").strip()[:60] or None
	db.commit()

	return {
		"conversation_id": conv.conversation_id,
		"answer": response.get("answer", ""),
		"sources": response.get("sources", []),
	}


