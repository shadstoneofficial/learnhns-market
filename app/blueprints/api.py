from flask import Blueprint, request, jsonify, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.models import db, Listing
from app.utils import validate_shakedex_proof, pin_to_ipfs, sanitize_html, send_gfavip_webhook
import os
import json
from datetime import datetime

api_bp = Blueprint('api', __name__)
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day"])

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
    
    listing = Listing(
        name=proof_data.get('name'),
        price_hns=proof_data.get('price'),
        description=description,
        seller_hns_address=proof_data.get('seller_address', 'unknown'),
        gfavip_user_id=gfavip_user_id,
        ipfs_cid=cid,
        proof_json=proof_data,
        expires_at=datetime.utcnow() # To be replaced with actual expiration from proof
    )
    
    db.session.add(listing)
    db.session.commit()
    
    send_gfavip_webhook(
        title="🎉 New HNS Listing!",
        message=f"**{listing.name}** — {listing.price_hns} HNS\n[View]({request.host_url}listing/{listing.name})"
    )
    
    return jsonify({"success": True, "name": listing.name, "cid": cid}), 201
