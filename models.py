from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, BigInteger, Float
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.sql import func
from contextlib import contextmanager
import datetime
from config import DATABASE_URL

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    telegram_username = Column(String, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    registration_date = Column(DateTime(timezone=True), server_default=func.now())
    referral_link_override = Column(String, nullable=True)
    referral_status_override = Column(Boolean, default=None, nullable=True)
    is_active = Column(Boolean, default=True)
    subscriptions = relationship("Subscription", back_populates="user")
    referrals_made = relationship("Referral", back_populates="referrer", foreign_keys="[Referral.user_id]")
    referrals_received = relationship("Referral", back_populates="referred_user", foreign_keys="[Referral.referred_user_id]")

class Subscription(Base):
    __tablename__ = 'subscriptions'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    start_date = Column(DateTime(timezone=True), server_default=func.now())
    end_date = Column(DateTime(timezone=True), nullable=False)
    payment_amount = Column(Integer, nullable=True)
    payment_id = Column(String, nullable=True, unique=True)
    auto_renewal = Column(Boolean, default=True)
    user = relationship("User", back_populates="subscriptions")

class Whitelist(Base):
    __tablename__ = 'whitelist'
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    added_date = Column(DateTime(timezone=True), server_default=func.now())

class PromoCode(Base):
    __tablename__ = "promo_codes"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    discount_percent = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    used_count = Column(Integer, default=0)
    max_uses = Column(Integer, nullable=True)

class Referral(Base):
    __tablename__ = 'referrals'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    referred_user_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    referrer = relationship("User", back_populates="referrals_made", foreign_keys=[user_id])
    referred_user = relationship("User", back_populates="referrals_received", foreign_keys=[referred_user_id])

class Admin(Base):
    __tablename__ = 'admins'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()