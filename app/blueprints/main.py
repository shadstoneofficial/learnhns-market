import json
from urllib.parse import quote

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from app.blueprints.api import get_hsd_status_payload
from app.blueprints.api import _active_listings_unique_by_name
from app.blueprints.api import _fetch_hsd_name_info
from app.blueprints.api import _name_transfer_status
from app.blueprints.api import _pending_listing_payload
from app.blueprints.api import _resolve_sale_pending_listing
from app.models import Listing, PendingListing

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    query = request.args.get('q', '')
    min_price = request.args.get('min_price')
    listings = _active_listings_unique_by_name()
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

@main_bp.route('/sold')
def sold():
    historical_statuses = ('sale-pending', 'sold', 'completed', 'archived', 'cancelled')
    listings = (
        Listing.query
        .filter(Listing.status.in_(historical_statuses))
        .order_by(Listing.created_at.desc())
        .all()
    )
    for listing in listings:
        _resolve_sale_pending_listing(listing)
    return render_template('sold.html', listings=listings)


@main_bp.route('/pending')
def pending():
    active_names = {
        listing.name
        for listing in _active_listings_unique_by_name()
    }
    pending_listings = [
        pending for pending in PendingListing.query.order_by(PendingListing.created_at.desc()).all()
        if pending.status not in {'active', 'cancelled', 'expired', 'failed'}
        and not pending.is_expired()
        and pending.name not in active_names
    ]
    return render_template(
        'pending_list.html',
        pending_listings=[_pending_listing_payload(pending) for pending in pending_listings],
    )


@main_bp.route('/upload')
def upload():
    return render_template('upload.html')

@main_bp.route('/docs')
def docs():
    return render_template('docs.html')


@main_bp.route('/admin')
def admin():
    return render_template('admin.html')


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
    normalized_name = name.lower().rstrip('/')
    listing_history = _listing_history(normalized_name)
    listing = _active_listings_unique_by_name()
    listing = next((row for row in listing if row.name == normalized_name), None)
    if not listing:
        pending = (
            PendingListing.query
            .filter_by(name=normalized_name)
            .order_by(PendingListing.created_at.desc())
            .first()
        )
        if pending and pending.status not in {'active', 'cancelled', 'expired', 'failed'} and not pending.is_expired():
            return render_template(
                'pending.html',
                pending=_pending_listing_payload(pending),
                listing_history=listing_history,
                hsd_readiness=_hsd_readiness(),
            )

        listing = (
            Listing.query
            .filter_by(name=normalized_name)
            .order_by(Listing.created_at.desc())
            .first()
        )
        if not listing:
            return render_template(
                'name_profile.html',
                profile=_name_profile_payload(normalized_name),
                listing_history=listing_history,
            )

    listing_is_expired = listing.is_expired()
    listing_display_status = 'expired' if listing_is_expired else listing.status
    listing_expires_at = listing.effective_expires_at()

    bob_deep_link = None
    if listing.status == 'active' and not listing_is_expired:
        proof_json = json.dumps(listing.proof_json, separators=(',', ':'))
        bob_deep_link = (
            f"bob-learnhns://x/fulfillauction?name={quote(listing.name, safe='')}"
            f"&presign={quote(proof_json, safe='')}"
        )

    return render_template(
        'listing.html',
        listing=listing,
        listing_display_status=listing_display_status,
        listing_expires_at=listing_expires_at,
        sale_transfer_status=_name_transfer_status(normalized_name),
        bob_deep_link=bob_deep_link,
        listing_history=listing_history,
        hsd_readiness=_hsd_readiness(),
    )


@main_bp.route('/listing/<name>/success')
def listing_success(name):
    normalized_name = name.lower().rstrip('/')
    tx_hash = request.args.get('tx', '').strip()
    listing = (
        Listing.query
        .filter_by(name=normalized_name)
        .order_by(Listing.created_at.desc())
        .first()
    )

    if not listing:
        return redirect(url_for('main.listing_detail', name=normalized_name))

    return render_template(
        'purchase_success.html',
        listing=listing,
        tx_hash=tx_hash,
    )


@main_bp.route('/listing/<name>/proof.json')
def listing_proof(name):
    normalized_name = name.lower().rstrip('/')
    listing = next(
        (row for row in _active_listings_unique_by_name() if row.name == normalized_name),
        None,
    )
    if listing is None:
        return jsonify({"error": "Active listing not found"}), 404
    return jsonify(listing.proof_json)


@main_bp.route('/pending/<name>')
def pending_detail(name):
    return redirect(url_for('main.listing_detail', name=name), code=301)


def _listing_history(name):
    historical_statuses = ('sale-pending', 'sold', 'completed', 'archived', 'cancelled')
    return (
        Listing.query
        .filter(Listing.name == name, Listing.status.in_(historical_statuses))
        .order_by(Listing.created_at.desc())
        .all()
    )


def _name_profile_payload(name):
    info, error = _fetch_hsd_name_info(name)
    if error:
        message, status = error[:2]
        return {
            "name": name,
            "found": False,
            "error": message,
            "statusCode": status,
            "info": {},
            "stats": {},
            "start": {},
        }

    payload = info if isinstance(info, dict) else {}
    name_info = payload.get('info') if isinstance(payload.get('info'), dict) else {}
    start_info = payload.get('start') if isinstance(payload.get('start'), dict) else {}
    stats = name_info.get('stats') if isinstance(name_info.get('stats'), dict) else {}
    return {
        "name": name,
        "found": bool(name_info),
        "info": name_info,
        "start": start_info,
        "stats": stats,
        "state": name_info.get('state'),
        "registered": name_info.get('registered'),
        "expired": name_info.get('expired'),
        "reserved": start_info.get('reserved'),
        "locked": start_info.get('locked'),
        "owner": name_info.get('owner') if isinstance(name_info.get('owner'), dict) else None,
        "renewalHeight": name_info.get('renewal'),
        "transferHeight": name_info.get('transfer'),
        "blocksUntilExpire": stats.get('blocksUntilExpire'),
        "daysUntilExpire": stats.get('daysUntilExpire'),
        "valueHns": name_info.get('value') / 1000000 if isinstance(name_info.get('value'), int) else None,
        "highestHns": name_info.get('highest') / 1000000 if isinstance(name_info.get('highest'), int) else None,
    }


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
