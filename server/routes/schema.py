# schema.py - SQLAlchemy tables + API schemas
import enum
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import Column, String, DateTime, Enum, Integer, create_engine, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import Literal, Optional, List

# Enum for user type
class UserType(enum.Enum):
	admin = "admin"
	user = "user"
	ruser = "ruser"


class ConversationMode(enum.Enum):
	public = "public"
	dual = "dual"

Base = declarative_base()

class User(Base):
	__tablename__ = "users"
	user_id = Column(Integer, primary_key=True, autoincrement=True)
	type = Column(Enum(UserType), nullable=False)
	username = Column(String, unique=True, nullable=False)
	password = Column(String, nullable=False)
	createdAt = Column(DateTime, default=datetime.now)


class ChatConversation(Base):
	__tablename__ = "chat_conversations"
	conversation_id = Column(Integer, primary_key=True, autoincrement=True)
	user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
	mode = Column(Enum(ConversationMode), nullable=False, index=True)
	title = Column(String, nullable=True)
	created_at = Column(DateTime, default=datetime.now, nullable=False)
	updated_at = Column(DateTime, default=datetime.now, nullable=False)

# Connect to local Postgres DB (update credentials as needed)
# Explicitly use psycopg v3 driver.
DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Drop and recreate tables (for schema changes)
def drop_tables():
	Base.metadata.drop_all(bind=engine)

def create_tables():
	Base.metadata.create_all(bind=engine)


# ===================== API (Pydantic) Schemas =====================

ConversationModeLiteral = Literal["public", "dual"]


class ConversationItem(BaseModel):
	conversation_id: int
	mode: ConversationModeLiteral
	title: Optional[str] = None
	created_at: datetime
	updated_at: datetime


class ConversationListResponse(BaseModel):
	items: List[ConversationItem]


class CreateConversationRequest(BaseModel):
	mode: Optional[ConversationModeLiteral] = None
	title: Optional[str] = None


class CreateConversationResponse(BaseModel):
	conversation_id: int
	mode: ConversationModeLiteral
	title: Optional[str] = None


class ChatMessage(BaseModel):
	role: Literal["user", "assistant"]
	content: str


class ConversationHistoryResponse(BaseModel):
	conversation_id: int
	mode: ConversationModeLiteral
	history: List[ChatMessage]


class SendMessageRequest(BaseModel):
	user_input: str


class SendMessageResponse(BaseModel):
	conversation_id: int
	answer: str
	sources: List[str]
