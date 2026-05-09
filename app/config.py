import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-prod')
    APP_ENV = os.getenv('APP_ENV', 'production')
    ALLOWED_PROOF_NETWORKS = [
        network.strip()
        for network in os.getenv('ALLOWED_PROOF_NETWORKS', 'main').split(',')
        if network.strip()
    ]
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///dev.db')
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    
    # Pinata
    PINATA_API_KEY = os.getenv('PINATA_API_KEY')
    PINATA_SECRET_KEY = os.getenv('PINATA_SECRET_KEY')
    
    # GFAVIP Webhook
    GFAVIP_WEBHOOK_URL = os.getenv('GFAVIP_WEBHOOK_URL')
    
    # Domain configuration
    # SERVER_NAME = os.getenv('SERVER_NAME', 'market.learnhns.com')
