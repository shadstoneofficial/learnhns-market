from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Listing(db.Model):
    __tablename__ = 'listings'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    price_hns = db.Column(db.Numeric(12, 6), nullable=False)
    description = db.Column(db.Text)
    
    seller_hns_address = db.Column(db.String(100), nullable=False)
    gfavip_user_id = db.Column(db.String(100), nullable=True)
    gfavip_username = db.Column(db.String(100), nullable=True)
    
    ipfs_cid = db.Column(db.String(100), nullable=False)
    proof_json = db.Column(db.JSON, nullable=False)
    
    status = db.Column(db.String(20), default='active', index=True)  # active, sold, cancelled, archived, flagged
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sold_at = db.Column(db.DateTime, nullable=True, index=True)
    sale_tx_hash = db.Column(db.String(64), nullable=True, index=True)
    cancelled_at = db.Column(db.DateTime, nullable=True, index=True)
    cancel_tx_hash = db.Column(db.String(64), nullable=True, index=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    flagged_reason = db.Column(db.Text, nullable=True)

    def effective_expires_at(self):
        if self.expires_at:
            return self.expires_at

        proof_data = self.proof_json or {}
        bids = proof_data.get('data') or []
        lock_times = [
            bid.get('lockTime')
            for bid in bids
            if isinstance(bid, dict) and isinstance(bid.get('lockTime'), int)
        ]

        if not lock_times:
            return None

        return datetime.utcfromtimestamp(max(lock_times))

    def is_expired(self):
        expires_at = self.effective_expires_at()
        return bool(expires_at and expires_at < datetime.utcnow())


class PendingListing(db.Model):
    __tablename__ = 'pending_listings'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    network = db.Column(db.String(20), default='main', nullable=False, index=True)
    transfer_tx_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    transfer_output_idx = db.Column(db.Integer, nullable=True)
    lock_script_addr = db.Column(db.String(100), nullable=True)
    listing_mode = db.Column(db.String(40), default='fixed-price', nullable=False)
    expected_price = db.Column(db.BigInteger, nullable=True)
    seller_note = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(40), default='pending-submitted', nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('name', 'network', name='uq_pending_listings_name_network'),
    )

    def is_expired(self):
        return self.expires_at and self.expires_at < datetime.utcnow()


class ExpiringNameWatch(db.Model):
    __tablename__ = 'expiring_name_watches'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    network = db.Column(db.String(20), default='main', nullable=False, index=True)
    source = db.Column(db.String(40), default='market-observed', nullable=False, index=True)
    state = db.Column(db.String(40), nullable=True, index=True)
    renewal_height = db.Column(db.Integer, nullable=True)
    expiration_height = db.Column(db.Integer, nullable=True, index=True)
    blocks_until_expire = db.Column(db.Integer, nullable=True, index=True)
    days_until_expire = db.Column(db.Numeric(12, 4), nullable=True)
    hours_until_expire = db.Column(db.Numeric(12, 4), nullable=True)
    expired = db.Column(db.Boolean, default=False, nullable=False, index=True)
    found = db.Column(db.Boolean, default=False, nullable=False, index=True)
    error = db.Column(db.Text, nullable=True)
    source_height = db.Column(db.Integer, nullable=True, index=True)
    last_checked_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('name', 'network', name='uq_expiring_name_watches_name_network'),
    )


class GlobalNameState(db.Model):
    __tablename__ = 'global_name_states'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    network = db.Column(db.String(20), default='main', nullable=False, index=True)
    state = db.Column(db.String(40), nullable=True, index=True)
    renewal_height = db.Column(db.Integer, nullable=True)
    expiration_height = db.Column(db.Integer, nullable=True, index=True)
    blocks_until_expire = db.Column(db.Integer, nullable=True, index=True)
    days_until_expire = db.Column(db.Numeric(12, 4), nullable=True)
    hours_until_expire = db.Column(db.Numeric(12, 4), nullable=True)
    expired = db.Column(db.Boolean, default=False, nullable=False, index=True)
    source_height = db.Column(db.Integer, nullable=True, index=True)
    last_checked_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('name', 'network', name='uq_global_name_states_name_network'),
    )


class NameIndexerProgress(db.Model):
    __tablename__ = 'name_indexer_progress'

    id = db.Column(db.Integer, primary_key=True)
    network = db.Column(db.String(20), default='main', nullable=False, unique=True, index=True)
    status = db.Column(db.String(40), default='not-started', nullable=False, index=True)
    last_indexed_height = db.Column(db.Integer, nullable=True, index=True)
    target_height = db.Column(db.Integer, nullable=True, index=True)
    names_indexed = db.Column(db.Integer, default=0, nullable=False)
    last_error = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
