from flask import Blueprint, request, jsonify, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests
from sqlalchemy.exc import IntegrityError
from app.models import db, Listing, PendingListing
from app.utils import (
    fixed_price_listing_fields,
    validate_shakedex_proof,
    pin_to_ipfs,
    sanitize_html,
    send_gfavip_webhook,
)
import os
import json
from datetime import datetime
from urllib.parse import urljoin

api_bp = Blueprint('api', __name__)
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day"])

SHAKEDEX_TRANSFER_LOCKUP = 288
PENDING_TERMINAL_STATUSES = {'active', 'cancelled', 'expired', 'failed'}


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


def _pending_listing_status(pending):
    if pending.is_expired():
        return {
            "status": "expired",
            "pendingReason": "Pending listing expired",
            "blocksUntilFinalize": None,
            "chainHeight": None,
            "transferHeight": None,
        }

    if pending.status in PENDING_TERMINAL_STATUSES:
        return {
            "status": pending.status,
            "pendingReason": "Pending listing is no longer awaiting finalization",
            "blocksUntilFinalize": None,
            "chainHeight": None,
            "transferHeight": None,
        }

    tx, tx_error = _fetch_hsd_tx(pending.transfer_tx_hash)
    if tx_error:
        status_code = tx_error[1]
        if status_code == 404:
            chain_payload, chain_status = get_hsd_status_payload()
            indexers = {}
            if chain_status == 200:
                indexers = ((chain_payload.get('chain') or {}).get('indexers') or {})
            if indexers.get('indexTX') is False:
                return _pending_status_from_name_info(pending, chain_payload, chain_status)
            return {
                "status": "pending-submitted",
                "pendingReason": "Waiting for transfer transaction to appear",
                "blocksUntilFinalize": None,
                "chainHeight": None,
                "transferHeight": None,
            }
        return {
            "status": pending.status or "pending-submitted",
            "pendingReason": "Could not refresh chain status",
            "blocksUntilFinalize": None,
            "chainHeight": None,
            "transferHeight": None,
        }

    tx_height = tx.get('height') if isinstance(tx, dict) else None
    if not isinstance(tx_height, int) or tx_height < 0:
        return {
            "status": "transfer-unconfirmed",
            "pendingReason": "Waiting for transfer confirmation",
            "blocksUntilFinalize": None,
            "chainHeight": None,
            "transferHeight": tx_height,
        }

    chain_payload, chain_status = get_hsd_status_payload()
    chain_height = chain_payload.get('height') if chain_status == 200 else None
    if not isinstance(chain_height, int):
        return {
            "status": "transfer-lockup",
            "pendingReason": "Transfer confirmed; waiting for chain status",
            "blocksUntilFinalize": None,
            "chainHeight": None,
            "transferHeight": tx_height,
        }

    blocks_since_transfer = max(chain_height - tx_height, 0)
    blocks_until_finalize = max((SHAKEDEX_TRANSFER_LOCKUP + 1) - blocks_since_transfer, 0)
    if blocks_until_finalize > 0:
        return {
            "status": "transfer-lockup",
            "pendingReason": "Waiting for Shakedex lock finalization",
            "blocksUntilFinalize": blocks_until_finalize,
            "chainHeight": chain_height,
            "transferHeight": tx_height,
        }

    return {
        "status": "ready-to-finalize",
        "pendingReason": "Ready for seller to finalize the Shakedex lock",
        "blocksUntilFinalize": 0,
        "chainHeight": chain_height,
        "transferHeight": tx_height,
    }


def _pending_status_from_name_info(pending, chain_payload=None, chain_status=None):
    name_info, name_error = _fetch_hsd_name_info(pending.name)
    chain_height = chain_payload.get('height') if chain_status == 200 else None

    if name_error:
        return {
            "status": "pending-submitted",
            "pendingReason": "Pending record received; this channel is not transaction-indexed, and name-state lookup is not available yet.",
            "blocksUntilFinalize": None,
            "chainHeight": chain_height,
            "transferHeight": None,
            "nameState": None,
        }

    info = name_info.get('info') if isinstance(name_info, dict) else None
    if not isinstance(info, dict):
        return {
            "status": "pending-submitted",
            "pendingReason": "Pending record received; no active on-chain name state is visible yet.",
            "blocksUntilFinalize": None,
            "chainHeight": chain_height,
            "transferHeight": None,
            "nameState": None,
        }

    stats = info.get('stats') if isinstance(info.get('stats'), dict) else {}
    transfer_height = info.get('transfer')
    if not isinstance(transfer_height, int) or transfer_height <= 0:
        return {
            "status": "pending-submitted",
            "pendingReason": "Pending record received; no active transfer lockup is visible for this name yet.",
            "blocksUntilFinalize": None,
            "chainHeight": chain_height,
            "transferHeight": None,
            "nameState": info.get('state'),
        }

    blocks_until_finalize = stats.get('blocksUntilValidFinalize')
    if not isinstance(blocks_until_finalize, int) and isinstance(chain_height, int):
        blocks_since_transfer = max(chain_height - transfer_height, 0)
        blocks_until_finalize = max(SHAKEDEX_TRANSFER_LOCKUP - blocks_since_transfer, 0)

    if isinstance(blocks_until_finalize, int) and blocks_until_finalize <= 0:
        return {
            "status": "ready-to-finalize",
            "pendingReason": "Transfer lockup is complete; seller can finalize the Shakedex lock and upload the proof.",
            "blocksUntilFinalize": 0,
            "chainHeight": chain_height,
            "transferHeight": transfer_height,
            "nameState": info.get('state'),
        }

    return {
        "status": "transfer-lockup",
        "pendingReason": "Transfer detected; waiting for Shakedex lockup before seller finalizes the proof.",
        "blocksUntilFinalize": blocks_until_finalize,
        "chainHeight": chain_height,
        "transferHeight": transfer_height,
        "nameState": info.get('state'),
    }


def _pending_listing_payload(pending, refresh=True):
    status_info = _pending_listing_status(pending) if refresh else {
        "status": pending.status,
        "pendingReason": None,
        "blocksUntilFinalize": None,
        "chainHeight": None,
        "transferHeight": None,
        "nameState": None,
    }

    return {
        "id": f"pending-{pending.id}",
        "name": pending.name,
        "network": pending.network,
        "status": status_info["status"],
        "buyable": False,
        "pending": True,
        "pendingReason": status_info["pendingReason"],
        "transferTxHash": pending.transfer_tx_hash,
        "transferOutputIdx": pending.transfer_output_idx,
        "lockScriptAddr": pending.lock_script_addr,
        "listingMode": pending.listing_mode,
        "expectedPrice": pending.expected_price,
        "blocksUntilFinalize": status_info["blocksUntilFinalize"],
        "chainHeight": status_info["chainHeight"],
        "transferHeight": status_info["transferHeight"],
        "nameState": status_info.get("nameState"),
        "sellerNote": pending.seller_note,
        "createdAt": pending.created_at.isoformat() if pending.created_at else None,
        "updatedAt": pending.updated_at.isoformat() if pending.updated_at else None,
        "url": f"/listing/{pending.name}",
    }


def _bob_auction_from_pending(pending):
    payload = _pending_listing_payload(pending)
    return {
        **payload,
        "bids": [],
        "data": [],
        "version": 2,
        "description": payload["pendingReason"],
        "url": f"/listing/{pending.name}",
    }


def _listing_is_available(listing):
    return listing and listing.status == 'active' and not listing.is_expired()


def _active_listing_for_name(name):
    return (
        Listing.query
        .filter_by(name=name, status='active')
        .order_by(Listing.created_at.desc())
        .first()
    )


def _listing_coin_ref(listing):
    proof = listing.proof_json
    return proof["lockingTxHash"], proof["lockingOutputIdx"]


def _tx_spends_listing_coin(tx, listing):
    tx_hash, output_index = _listing_coin_ref(listing)
    inputs = tx.get('inputs', []) if isinstance(tx, dict) else []

    for tx_input in inputs:
        prevout = tx_input.get('prevout') if isinstance(tx_input, dict) else None
        if not isinstance(prevout, dict):
            continue

        prev_hash = prevout.get('hash')
        prev_index = prevout.get('index')
        try:
            prev_index = int(prev_index)
        except (TypeError, ValueError):
            continue

        if prev_hash == tx_hash and prev_index == int(output_index):
            return True

    return False


def _validate_hex_hash(value, field):
    tx_hash = str(value or '').strip().lower()
    if not tx_hash:
        return None, None
    if len(tx_hash) != 64 or any(c not in '0123456789abcdef' for c in tx_hash):
        return None, (f"{field} must be a 64-character hex string", 400)
    return tx_hash, None


def _verified_listing_spend(tx_hash, listing):
    tx, error = _fetch_hsd_tx(tx_hash)
    if error:
        message, status = error[:2]
        return None, {"error": message}, status

    if not _tx_spends_listing_coin(tx, listing):
        return None, {
            "error": "Transaction does not spend this listing's Shakedex locking coin",
            "url": f"/listing/{listing.name}",
        }, 400

    return tx, None, 200


def _mark_listing_sold_if_spent(listing, sale_tx_hash=None):
    tx_hash, output_index = _listing_coin_ref(listing)

    if sale_tx_hash:
        _, payload, status = _verified_listing_spend(sale_tx_hash, listing)
        if status != 200:
            return False, payload, status

        listing.status = 'sold'
        listing.sold_at = datetime.utcnow()
        listing.sale_tx_hash = sale_tx_hash
        db.session.commit()
        return True, {
            "sold": True,
            "status": listing.status,
            "soldAt": listing.sold_at.isoformat(),
            "saleTxHash": listing.sale_tx_hash,
            "url": f"/listing/{listing.name}",
        }, 200

    coin, error = _fetch_hsd_coin(tx_hash, output_index)

    if error:
        message, status = error[:2]
        if status != 404:
            return False, {"error": message}, status

        return False, {
            "sold": False,
            "status": "spent-unverified",
            "message": "The Shakedex locking coin is no longer available. Submit a saleTxHash to verify this was a sale before recording sale history.",
            "url": f"/listing/{listing.name}",
        }, 200

    return False, {
        "sold": False,
        "status": listing.status,
        "coin": coin,
        "url": f"/listing/{listing.name}",
    }, 200


def _mark_listing_cancelled_if_spent(listing, cancel_tx_hash):
    if not cancel_tx_hash:
        return False, {"error": "cancelTxHash is required to record a cancelled listing"}, 400

    _, payload, status = _verified_listing_spend(cancel_tx_hash, listing)
    if status != 200:
        return False, payload, status

    listing.status = 'cancelled'
    listing.cancelled_at = datetime.utcnow()
    listing.cancel_tx_hash = cancel_tx_hash
    db.session.commit()
    return True, {
        "cancelled": True,
        "status": listing.status,
        "cancelledAt": listing.cancelled_at.isoformat(),
        "cancelTxHash": listing.cancel_tx_hash,
        "url": f"/listing/{listing.name}",
    }, 200


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


def _hsd_rpc_request(method, params=None):
    if _hsd_api_style() == 'firehsd':
        return None, ("HSD RPC is not available for Fire HSD endpoints", 503, None)

    hsd_url = current_app.config.get('HSD_HTTP_URL')
    api_key = current_app.config.get('HSD_API_KEY')

    if not hsd_url:
        return None, ("HSD HTTP URL is not configured", 503, None)

    url = hsd_url.rstrip('/') + '/'
    auth = ('x', api_key) if api_key else None
    body = {
        "jsonrpc": "2.0",
        "id": "learnhns-market",
        "method": method,
        "params": params or [],
    }

    try:
        response = requests.post(
            url,
            auth=auth,
            json=body,
            timeout=current_app.config.get('HSD_HTTP_TIMEOUT', 5),
        )
    except requests.RequestException as exc:
        current_app.logger.warning("Failed HSD RPC %s: %s", method, exc)
        return None, ("Could not reach HSD node", 503, str(exc))

    if response.status_code == 401:
        return None, ("HSD API key is invalid", 503, response.text[:500])
    if response.status_code >= 400:
        current_app.logger.warning(
            "HSD RPC failed for %s with status %s: %s",
            method,
            response.status_code,
            response.text[:500],
        )
        return None, ("HSD RPC request failed", 503, response.text[:500])

    try:
        data = response.json()
    except ValueError:
        return None, ("HSD returned invalid JSON", 503, response.text[:500])

    if isinstance(data, dict) and data.get('error'):
        error = data.get('error') or {}
        message = error.get('message') or "HSD RPC returned an error"
        return None, (message, 404 if "not found" in message.lower() else 503, error)

    return data.get('result') if isinstance(data, dict) else data, None


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


def _fetch_hsd_name_info(name):
    info, error = _hsd_rpc_request('getnameinfo', [name, True])
    if error and error[1] == 404:
        return None, ("Name was not found", 404, error[2])
    return info, error


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
    active_names = {listing.name for listing in active_listings}
    pending_listings = [
        pending for pending in PendingListing.query.order_by(PendingListing.created_at.desc()).all()
        if pending.status not in PENDING_TERMINAL_STATUSES
        and not pending.is_expired()
        and pending.name not in active_names
    ]
    all_rows = [
        *[_bob_auction_from_pending(pending) for pending in pending_listings],
        *[_bob_auction_from_listing(listing) for listing in active_listings],
    ]
    total = len(all_rows)
    start = (page - 1) * per_page
    end = start + per_page

    return jsonify({
        "total": total,
        "auctions": all_rows[start:end],
    })


@api_bp.route('/v2/sales', methods=['GET'])
def sales():
    sold_statuses = ('sold', 'completed', 'archived')
    listings = (
        Listing.query
        .filter(Listing.status.in_(sold_statuses))
        .order_by(Listing.created_at.desc())
        .all()
    )

    return jsonify({
        "total": len(listings),
        "sales": [
            {
                "id": listing.id,
                "name": listing.name,
                "priceHns": float(listing.price_hns),
                "status": listing.status,
                "createdAt": listing.created_at.isoformat() if listing.created_at else None,
                "soldAt": listing.sold_at.isoformat() if listing.sold_at else None,
                "saleTxHash": listing.sale_tx_hash,
                "expiresAt": listing.expires_at.isoformat() if listing.expires_at else None,
                "url": f"/listing/{listing.name}",
            }
            for listing in listings
        ],
    })


@api_bp.route('/v2/pending-listings', methods=['GET'])
def pending_listings():
    pending = [
        row for row in PendingListing.query.order_by(PendingListing.created_at.desc()).all()
        if row.status not in PENDING_TERMINAL_STATUSES and not row.is_expired()
    ]
    return jsonify({
        "total": len(pending),
        "pending": [_pending_listing_payload(row) for row in pending],
    })


@api_bp.route('/v2/pending-listings', methods=['POST'])
@limiter.limit("20 per hour")
def create_pending_listing():
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip().lower().rstrip('/')
    network = str(data.get('network', 'main')).strip().lower()
    transfer_tx_hash = str(data.get('transferTxHash', data.get('transfer_tx_hash', ''))).strip().lower()

    if not name:
        return jsonify({"error": "name is required"}), 400
    if network not in {'main', 'testnet', 'regtest', 'simnet'}:
        return jsonify({"error": "network is invalid"}), 400
    if len(transfer_tx_hash) != 64 or any(c not in '0123456789abcdef' for c in transfer_tx_hash):
        return jsonify({"error": "transferTxHash must be a 64-character hex string"}), 400

    transfer_output_idx = data.get('transferOutputIdx', data.get('transfer_output_idx'))
    if transfer_output_idx is not None:
        try:
            transfer_output_idx = int(transfer_output_idx)
        except (TypeError, ValueError):
            return jsonify({"error": "transferOutputIdx must be an integer"}), 400
        if transfer_output_idx < 0:
            return jsonify({"error": "transferOutputIdx must be non-negative"}), 400

    expected_price = data.get('expectedPrice', data.get('expected_price'))
    if expected_price in ('', None):
        expected_price = None
    else:
        try:
            expected_price = int(expected_price)
        except (TypeError, ValueError):
            return jsonify({"error": "expectedPrice must be an integer in base HNS units"}), 400
        if expected_price < 0:
            return jsonify({"error": "expectedPrice must be non-negative"}), 400

    pending = PendingListing.query.filter_by(name=name, network=network).first()
    if pending is None:
        pending = PendingListing(name=name, network=network, transfer_tx_hash=transfer_tx_hash)

    pending.transfer_tx_hash = transfer_tx_hash
    pending.transfer_output_idx = transfer_output_idx
    pending.lock_script_addr = data.get('lockScriptAddr', data.get('lock_script_addr'))
    pending.listing_mode = data.get('listingMode', data.get('listing_mode')) or 'fixed-price'
    pending.expected_price = expected_price
    pending.seller_note = sanitize_html(data.get('sellerNote', data.get('seller_note', '')))
    pending.status = 'pending-submitted'

    try:
        db.session.add(pending)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "A pending listing with that transferTxHash already exists"}), 409

    return jsonify({
        "success": True,
        "pending": _pending_listing_payload(pending),
    }), 201


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
    listing = _active_listing_for_name(name)
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


@api_bp.route('/v2/listings/<name>/refresh-status', methods=['GET', 'POST'])
def refresh_listing_status(name):
    listing = _active_listing_for_name(name.lower().rstrip('/'))
    if not _listing_is_available(listing):
        return jsonify({"error": "Active listing not found"}), 404

    data = request.get_json(silent=True) or {}
    request_values = {**request.args.to_dict(), **data}
    sale_tx_hash, sale_hash_error = _validate_hex_hash(
        request_values.get('saleTxHash', request_values.get('sale_tx_hash')),
        'saleTxHash',
    )
    if sale_hash_error:
        message, status = sale_hash_error
        return jsonify({"error": message}), status

    cancel_tx_hash, cancel_hash_error = _validate_hex_hash(
        request_values.get('cancelTxHash', request_values.get('cancel_tx_hash')),
        'cancelTxHash',
    )
    if cancel_hash_error:
        message, status = cancel_hash_error
        return jsonify({"error": message}), status

    outcome = str(request_values.get('outcome', request_values.get('status', 'sold' if sale_tx_hash else 'refresh'))).strip().lower()
    if outcome in {'cancelled', 'canceled', 'cancel'}:
        _, payload, status = _mark_listing_cancelled_if_spent(listing, cancel_tx_hash)
        return jsonify(payload), status

    _, payload, status = _mark_listing_sold_if_spent(listing, sale_tx_hash or None)
    return jsonify(payload), status


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


@api_bp.route('/v2/names/<name>/status', methods=['GET'])
def name_status(name):
    info, error = _fetch_hsd_name_info(name)
    if error:
        message, status = error[:2]
        return jsonify({"error": message}), status

    return jsonify({
        "name": name,
        "found": bool(isinstance(info, dict) and info.get('info')),
        "nameInfo": info,
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
    existing_active = Listing.query.filter_by(name=listing_fields['name'], status='active').first()
    if existing_active and not existing_active.is_expired():
        return jsonify({"error": f"An active listing for {listing_fields['name']} already exists"}), 409

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
        pending = PendingListing.query.filter_by(name=listing.name).first()
        if pending:
            pending.status = 'active'
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": f"A listing for {listing.name} already exists"}), 409
    
    send_gfavip_webhook(
        title="🎉 New HNS Listing!",
        message=f"**{listing.name}** — {listing.price_hns} HNS\n[View]({request.host_url}listing/{listing.name})"
    )
    
    return jsonify({"success": True, "name": listing.name, "cid": cid}), 201
