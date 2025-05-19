# models.py
from sqlalchemy import (Column, Integer, String, DateTime, Boolean, create_engine)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=True)      # optional link to original image
    order_id = Column(String, unique=True, index=True, nullable=False)
    date = Column(String, nullable=True)
    total = Column(String, nullable=True)
    # … add any other fields your GPT might produce …
    collected = Column(Boolean, default=False)
    last_updated = Column(DateTime, nullable=True)  # if you want to track update time

# SQLite in-memory or file‐based
DATABASE_URL = "sqlite:///./orders.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
