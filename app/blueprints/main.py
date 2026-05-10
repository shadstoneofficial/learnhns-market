import json
from urllib.parse import quote

from flask import Blueprint, jsonify, render_template, request
from app.blueprints.api import get_hsd_status_payload
from app.blueprints.api import _pending_listing_payload
from app.models import Listing, PendingListing

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    query = request.args.get('q', '')
    min_price = request.args.get('min_price')
    # Basic active listings query
    listings = Listing.query.filter_by(status='active').order_by(Listing.created_at.desc()).all()
    active_names = {listing.name for listing in listings}
    pending_listings = [
        pending for pending in PendingListing.query.order_by(PendingListing.created_at.desc()).all()
        if pending.status not in {'active', 'cancelled', 'expired', 'failed'}
        and not pending.is_expired()
        and pending.name not in active_names
    ]
    return render_template(
        'index.html',
        listings=listings,
        pending_listings=[_pending_listing_payload(pending) for pending in pending_listings],
        hsd_readiness=_hsd_readiness(),
    )

@main_bp.route('/upload')
def upload():
    return render_template('upload.html')

@main_bp.route('/docs')
def docs():
    return render_template('docs.html')

@main_bp.route('/status')
def status():
    status_data, _ = get_hsd_status_payload()
    progress = status_data.get('progress')
    progress_percent = None
    if isinstance(progress, (int, float)):
        progress_percent = max(0, min(100, progress * 100))

    return render_template(
        'status.html',
        status=status_data,
        progress_percent=progress_percent,
    )

@main_bp.route('/listing/<name>')
def listing_detail(name):
    listing = Listing.query.filter_by(name=name, status='active').first_or_404()
    proof_json = json.dumps(listing.proof_json, separators=(',', ':'))
    bob_deep_link = (
        f"bob://x/fulfillauction?name={quote(listing.name, safe='')}"
        f"&presign={quote(proof_json, safe='')}"
    )
    return render_template(
        'listing.html',
        listing=listing,
        bob_deep_link=bob_deep_link,
        hsd_readiness=_hsd_readiness(),
    )

@main_bp.route('/listing/<name>/proof.json')
def listing_proof(name):
    listing = Listing.query.filter_by(name=name, status='active').first_or_404()
    return jsonify(listing.proof_json)


@main_bp.route('/pending/<name>')
def pending_detail(name):
    pending = PendingListing.query.filter_by(name=name).first_or_404()
    return render_template(
        'pending.html',
        pending=_pending_listing_payload(pending),
        hsd_readiness=_hsd_readiness(),
    )


def _hsd_readiness():
    status_data, _ = get_hsd_status_payload()
    progress = status_data.get('progress')
    progress_percent = None
    if isinstance(progress, (int, float)):
        progress_percent = max(0, min(100, progress * 100))

    return {
        "reachable": status_data.get('reachable', False),
        "ready": status_data.get('reachable', False) and isinstance(progress, (int, float)) and progress >= 0.99,
        "height": status_data.get('height'),
        "progress_percent": progress_percent,
        "error": status_data.get('error'),
    }
