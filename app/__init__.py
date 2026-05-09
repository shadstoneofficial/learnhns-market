from flask import Flask
from flask_migrate import Migrate
from flask_cors import CORS
from app.config import Config
from app.models import db
from app.blueprints.main import main_bp
from app.blueprints.api import api_bp
import os

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(Config)
    
    db.init_app(app)
    Migrate(app, db)
    CORS(app)
    
    # Blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Create upload folder
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    return app
