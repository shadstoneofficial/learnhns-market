from flask import Blueprint, request, jsonify, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests
from sqlalchemy.exc import IntegrityError
from app.models import db, Listing
from app.utils import (
    fixed_price_listing_fields,
    validate_shakedex_proof,
    pin_to_ipfs,
    sanitize_html,
    send_gfavip_webhook,
)
import os
import json
from urllib.parse import urljoin

api_bp = Blueprint('api', __name__)
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day"])


def _bob_auction_from_listing(listing):
    proof = listing.proof_json
    bids = proof.get('data', [])
    return {
        "id": listing.id,
        "name": proof["name"],
        "lockingTxHash": proof["lockingTxHash"],
        "lockingOutputIdx": proof["lockingOutputIdx"],
        "publicKey": proof["publicKey"],
        "paymentAddr": proof["paymentAddr"],
        "feeAddr": proof.get("feeAddr"),
        "bids": bids,
        "data": bids,
        "version": proof.get("version", 2),
        "description": listing.description,
        "createdAt": listing.created_at.isoformat() if listing.created_at else None,
        "expiresAt": listing.expires_at.isoformat() if listing.expires_at else None,
        "url": f"/listing/{listing.name}",
    }


def _listing_is_available(listing):
    return listing and listing.status == 'active' and not listing.is_expired()


def _hsd_api_style():
    style = current_app.config.get('HSD_API_STYLE', 'raw')
    return style.lower()


def _hsd_endpoint(endpoint):
    if _hsd_api_style() != 'firehsd':
        return endpoint

    normalized = endpoint.strip('/')
    if not normalized:
        return '/api/v1/status'
    return f"/api/v1/{normalized}"


def _hsd_request(endpoint, method='GET', payload=None):
    hsd_url = current_app.config.get('HSD_HTTP_URL')
    api_key = current_app.config.get('HSD_API_KEY')

    if not hsd_url:
        return None, ("HSD HTTP URL is not configured", 503, None)

    mapped_endpoint = _hsd_endpoint(endpoint)
    url = urljoin(hsd_url.rstrip('/') + '/', mapped_endpoint.lstrip('/'))
    auth = ('x', api_key) if api_key and _hsd_api_style() != 'firehsd' else None

    try:
        response = requests.request(
            method,
            url,
            auth=auth,
            json=payload,
            timeout=current_app.config.get('HSD_HTTP_TIMEOUT', 5),
        )
    except requests.RequestException as exc:
        current_app.logger.warning("Failed HSD request %s %s: %s", method, mapped_endpoint, exc)
        return None, ("Could not reach HSD node", 503, str(exc))

    if response.status_code == 404:
        return None, ("HSD resource not found", 404, response.text[:500])
    if response.status_code == 401:
        return None, ("HSD API key is invalid", 503, response.text[:500])
    if response.status_code >= 400:
        current_app.logger.warning(
            "HSD request failed for %s %s with status %s: %s",
            method,
            mapped_endpoint,
            response.status_code,
            response.text[:500],
        )
        return None, ("HSD request failed", 503, response.text[:500])

    try:
        return response.json(), None
    except ValueError:
        return None, ("HSD returned invalid JSON", 503, response.text[:500])


def _fetch_hsd_coin(tx_hash, output_index):
    coin, error = _hsd_request(f"/coin/{tx_hash}/{output_index}")
    if error and error[1] == 404:
        return None, ("Listing coin was not found or is already spent", 404, error[2])
    return coin, error


def _fetch_hsd_tx(tx_hash):
    tx, error = _hsd_request(f"/tx/{tx_hash}")
    if error and error[1] == 404:
        return None, ("Transaction was not found", 404, error[2])
    return tx, error


@api_bp.route('/v1/fee_info', methods=['GET'])
@api_bp.route('/v2/fee_info', methods=['GET'])
def fee_info():
    rate = current_app.config['MARKETPLACE_FEE_RATE']
    address = current_app.config['MARKETPLACE_FEE_ADDRESS']
    if rate < 0 or rate > 10000:
        return jsonify({"error": "Marketplace fee rate is invalid"}), 503
    if rate > 0 and not address:
        return jsonify({"error": "Marketplace fee address is not configured"}), 503

    return jsonify({
        "rate": rate,
        "address": address,
        "addr": address,
    })


@api_bp.route('/v2/auctions', methods=['GET'])
def auctions():
    try:
        page = max(int(request.args.get('page', 1)), 1)
        per_page = min(max(int(request.args.get('per_page', 20)), 1), 100)
    except ValueError:
        return jsonify({"error": "Invalid pagination"}), 400

    active_listings = [
        listing for listing in Listing.query.filter_by(status='active').order_by(Listing.created_at.desc()).all()
        if not listing.is_expired()
    ]
    total = len(active_listings)
    start = (page - 1) * per_page
    end = start + per_page
    page_listings = active_listings[start:end]

    return jsonify({
        "total": total,
        "auctions": [_bob_auction_from_listing(listing) for listing in page_listings],
    })


@api_bp.route('/v2/hsd/status', methods=['GET'])
def hsd_status():
    payload, status = get_hsd_status_payload()
    return jsonify(payload), status


def get_hsd_status_payload():
    hsd_url = current_app.config.get('HSD_HTTP_URL')
    configured = bool(hsd_url)
    api_style = _hsd_api_style()

    if not configured:
        return {
            "configured": False,
            "reachable": False,
            "error": "HSD HTTP URL is not configured",
        }, 503

    info, error = _hsd_request('/')
    if error:
        message, status, detail = error
        return {
            "configured": True,
            "reachable": False,
            "url": hsd_url,
            "apiStyle": api_style,
            "error": message,
            "detail": detail,
        }, status

    if api_style == 'firehsd':
        chain_payload, chain_error = _hsd_request('/chain')
        if chain_error:
            message, status, detail = chain_error
            return {
                "configured": True,
                "reachable": False,
                "url": hsd_url,
                "apiStyle": api_style,
                "error": message,
                "detail": detail,
            }, status
        chain = chain_payload.get('chain', {}) if isinstance(chain_payload, dict) else {}
    else:
        chain = info.get('chain', {}) if isinstance(info, dict) else {}

    network = 'main' if api_style == 'firehsd' else (
        info.get('network') if isinstance(info, dict) else None
    )

    return {
        "configured": True,
        "reachable": True,
        "url": hsd_url,
        "apiStyle": api_style,
        "network": network,
        "version": info.get('version') if isinstance(info, dict) else None,
        "chain": chain,
        "height": chain.get('height'),
        "progress": chain.get('progress'),
    }, 200


@api_bp.route('/v2/listings/<name>/coin', methods=['GET'])
def listing_coin(name):
    listing = Listing.query.filter_by(name=name).first()
    if not _listing_is_available(listing):
        return jsonify({"error": "Listing not found"}), 404

    proof = listing.proof_json
    tx_hash = proof["lockingTxHash"]
    output_index = proof["lockingOutputIdx"]
    coin, error = _fetch_hsd_coin(tx_hash, output_index)

    if error:
        message, status = error[:2]
        return jsonify({"error": message}), status

    return jsonify({
        "name": listing.name,
        "lockingTxHash": tx_hash,
        "lockingOutputIdx": output_index,
        "coin": coin,
    })


@api_bp.route('/v2/tx/<tx_hash>/status', methods=['GET'])
def tx_status(tx_hash):
    tx, error = _fetch_hsd_tx(tx_hash)
    if error:
        message, status = error[:2]
        return jsonify({"error": message}), status

    chain_payload, status = get_hsd_status_payload()
    chain_height = chain_payload.get('height') if status == 200 else None
    tx_height = tx.get('height') if isinstance(tx, dict) else None
    confirmations = tx.get('confirmations') if isinstance(tx, dict) else None
    if confirmations is None and isinstance(chain_height, int) and isinstance(tx_height, int) and tx_height >= 0:
        confirmations = max(chain_height - tx_height + 1, 0)

    return jsonify({
        "hash": tx_hash,
        "found": True,
        "confirmed": isinstance(tx_height, int) and tx_height >= 0,
        "height": tx_height,
        "confirmations": confirmations,
        "block": tx.get('block') if isinstance(tx, dict) else None,
        "mtime": tx.get('mtime') if isinstance(tx, dict) else None,
        "fee": tx.get('fee') if isinstance(tx, dict) else None,
        "chainHeight": chain_height,
        "tx": tx,
    })

@api_bp.route('/upload-proof', methods=['POST'])
@limiter.limit("10 per hour")  # per IP
def upload_proof():
    if 'proof' not in request.files:
        return jsonify({"error": "No proof file"}), 400
    
    file = request.files['proof']
    description = sanitize_html(request.form.get('description', ''))
    gfavip_user_id = request.form.get('gfavip_user_id')  # optional
    
    # Save temp
    temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file.filename)
    file.save(temp_path)
    
    try:
        with open(temp_path) as f:
            proof_data = json.load(f)
    except json.JSONDecodeError:
        os.remove(temp_path)
        return jsonify({"error": "Invalid JSON format"}), 400
    
    valid, msg = validate_shakedex_proof(proof_data)
    if not valid:
        os.remove(temp_path)
        return jsonify({"error": msg}), 400
    
    # Pin to IPFS
    try:
        cid = pin_to_ipfs(temp_path)
    except Exception as e:
        os.remove(temp_path)
        return jsonify({"error": f"Failed to pin to IPFS: {str(e)}"}), 500
        
    os.remove(temp_path)
    
    listing_fields = fixed_price_listing_fields(proof_data)
    listing = Listing(
        name=listing_fields['name'],
        price_hns=listing_fields['price_hns'],
        description=description,
        seller_hns_address=listing_fields['seller_hns_address'],
        gfavip_user_id=gfavip_user_id,
        ipfs_cid=cid,
        proof_json=proof_data,
        expires_at=listing_fields['expires_at']
    )
    
    try:
        db.session.add(listing)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": f"A listing for {listing.name} already exists"}), 409
    
    send_gfavip_webhook(
        title="🎉 New HNS Listing!",
        message=f"**{listing.name}** — {listing.price_hns} HNS\n[View]({request.host_url}listing/{listing.name})"
    )
    
    return jsonify({"success": True, "name": listing.name, "cid": cid}), 201
