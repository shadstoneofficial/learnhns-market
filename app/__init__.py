from flask import Flask, render_template
from flask_migrate import Migrate
from flask_cors import CORS
from app.config import Config
from app.models import db
from app.blueprints.main import main_bp
from app.blueprints.api import api_bp
from app.blueprints.account import account_bp
from app.blueprints.support_wall import support_wall_bp
from app.auth import current_account
import os

def display_name(name):
    decoded = decoded_name(name)
    if decoded == name:
        return name
    return f"{decoded} {name}"


def decoded_name(name):
    if not isinstance(name, str) or not name.startswith('xn--'):
        return name
    try:
        return name.encode('ascii').decode('idna')
    except UnicodeError:
        return name


def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(Config)
    
    db.init_app(app)
    Migrate(app, db)
    CORS(app)
    
    # Blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(support_wall_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    @app.context_processor
    def inject_current_account():
        return {
            'current_account': current_account(),
            'display_name': display_name,
            'decoded_name': decoded_name,
        }

    @app.errorhandler(404)
    def not_found(error):
        return render_template('404.html'), 404
    
    # Create upload folder
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    return app
