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

    # Marketplace fee policy.
    # Rate is expressed in basis points: 250 = 2.5%, 100 = 1%.
    MARKETPLACE_FEE_RATE = int(os.getenv('MARKETPLACE_FEE_RATE', '0'))
    MARKETPLACE_FEE_ADDRESS = os.getenv('MARKETPLACE_FEE_ADDRESS')

    # Optional full/indexed hsd node used to serve chain data to SPV clients.
    # Example raw hsd: HSD_HTTP_URL=http://127.0.0.1:12037 HSD_API_KEY=hunter2
    # Example Fire HSD: HSD_HTTP_URL=https://hsd.hns.au HSD_API_STYLE=firehsd
    HSD_HTTP_URL = os.getenv('HSD_HTTP_URL')
    HSD_API_KEY = os.getenv('HSD_API_KEY')
    HSD_API_STYLE = os.getenv('HSD_API_STYLE', 'raw')
    HSD_HTTP_TIMEOUT = float(os.getenv('HSD_HTTP_TIMEOUT', '5'))
    
    # Domain configuration
    # SERVER_NAME = os.getenv('SERVER_NAME', 'market.learnhns.com')
