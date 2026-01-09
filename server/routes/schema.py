# schema.py - SQLAlchemy User table definition
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Enum, Integer, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Enum for user type
class UserType(enum.Enum):
	admin = "admin"
	user = "user"
	ruser = "ruser"

Base = declarative_base()

class User(Base):
	__tablename__ = "users"
	id = Column(Integer, primary_key=True, autoincrement=True)
	type = Column(Enum(UserType), nullable=False)
	username = Column(String, unique=True, nullable=False)
	password = Column(String, nullable=False)
	createdAt = Column(DateTime, default=datetime.utcnow)

# Connect to local Postgres DB (update credentials as needed)
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/postgres"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
def create_tables():
	Base.metadata.create_all(bind=engine)
