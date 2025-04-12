import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = "8139120177:AAHujI9lO-iTEScy1w-QOyTZM7fMzVbkyaU"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "123123"

ADMIN_TG_ACCOUNT = os.getenv("ADMIN_TG_ACCOUNT")

DEFAULT_REFERRAL_STATUS = os.getenv("DEFAULT_REFERRAL_STATUS", "true").lower() == "true"

BOT_USERNAME = os.getenv("BOT_USERNAME", "sistemnik_helper_bot")

COMPANY_NAME = os.getenv("COMPANY_NAME", "Your Company Name")
COMPANY_REGISTRATION_NUMBER = os.getenv("COMPANY_REGISTRATION_NUMBER", "123456789")
COMPANY_ADDRESS = os.getenv("COMPANY_ADDRESS", "Company Address")
COMPANY_BANK = os.getenv("COMPANY_BANK", "Bank Name")
COMPANY_ACCOUNT = os.getenv("COMPANY_ACCOUNT", "123456789012")
COMPANY_SWIFT = os.getenv("COMPANY_SWIFT", "SWIFTCODE")
COMPANY_IBAN = os.getenv("COMPANY_IBAN", "IBAN123456789")

MERCHANT_ID = "your_merchant_id"
MERCHANT_SECRET_KEY = "your_secret_key"
PAYMENT_SUCCESS_URL = "https://your-site.com/success"
PAYMENT_FAIL_URL = "https://your-site.com/fail"
PAYMENT_NOTIFICATION_URL = "https://your-site.com/payment/callback"

ADMIN_SECRET_KEY = "your-secret-key-here"

if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("Warning: BOT_TOKEN is not set in .env file. Please set it.")

if ADMIN_PASSWORD == "password":
    print("Warning: Default ADMIN_PASSWORD is used. Please change it in .env file for security.")

if ADMIN_TG_ACCOUNT == "Illovesme" and not os.getenv("ADMIN_TG_ACCOUNT"):
    print("Info: Using default ADMIN_TG_ACCOUNT (@Illovesme). You can set your own in the .env file.") 
