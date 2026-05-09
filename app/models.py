from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Listing(db.Model):
    __tablename__ = 'listings'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False, index=True)
    price_hns = db.Column(db.Numeric(12, 6), nullable=False)
    description = db.Column(db.Text)
    
    seller_hns_address = db.Column(db.String(100), nullable=False)
    gfavip_user_id = db.Column(db.String(100), nullable=True)
    gfavip_username = db.Column(db.String(100), nullable=True)
    
    ipfs_cid = db.Column(db.String(100), nullable=False)
    proof_json = db.Column(db.JSON, nullable=False)
    
    status = db.Column(db.String(20), default='active', index=True)  # active, archived, flagged
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    flagged_reason = db.Column(db.Text, nullable=True)

    def is_expired(self):
        return self.expires_at and self.expires_at < datetime.utcnow()
