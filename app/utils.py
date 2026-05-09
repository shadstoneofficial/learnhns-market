import requests
import bleach
from flask import current_app
from decimal import Decimal
import re

HNS_BASE_UNITS = Decimal("1000000")
HEX_RE = re.compile(r'^[a-f0-9]+$', re.IGNORECASE)
ADDRESS_RE = re.compile(r'^(hs|rs|ts|ss)1[a-zA-HJ-NP-Z0-9]{25,39}$', re.IGNORECASE)

def sanitize_html(text):
    if not text:
        return ""
    return bleach.clean(text, tags=['b', 'i', 'a', 'br'], strip=True)

def send_gfavip_webhook(title: str, message: str, color: str = "#10b981"):
    url = current_app.config.get('GFAVIP_WEBHOOK_URL')
    if not url:
        return
    payload = {
        "title": title,
        "message": message,
        "color": color
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass  # fail gracefully

def pin_to_ipfs(file_path: str) -> str:
    url = "https://api.pinata.cloud/pinning/pinFileToIPFS"
    headers = {
        "pinata_api_key": current_app.config['PINATA_API_KEY'],
        "pinata_secret_api_key": current_app.config['PINATA_SECRET_KEY']
    }
    with open(file_path, 'rb') as f:
        response = requests.post(url, files={'file': f}, headers=headers)
    response.raise_for_status()
    return response.json()['IpfsHash']

def _is_hex(value, length):
    return isinstance(value, str) and len(value) == length and bool(HEX_RE.match(value))

def validate_shakedex_proof(proof_data: dict) -> tuple[bool, str]:
    try:
        required = [
            'version',
            'name',
            'lockingTxHash',
            'lockingOutputIdx',
            'publicKey',
            'paymentAddr',
            'data',
        ]
        if not all(k in proof_data for k in required):
            return False, "Missing required Shakedex proof fields"
        if proof_data['version'] != 2:
            return False, "Unsupported Shakedex proof version"
        if not isinstance(proof_data['name'], str) or not proof_data['name']:
            return False, "Invalid name"
        if not _is_hex(proof_data['lockingTxHash'], 64):
            return False, "Invalid locking transaction hash"
        if not isinstance(proof_data['lockingOutputIdx'], int) or proof_data['lockingOutputIdx'] < 0:
            return False, "Invalid locking output index"
        if not _is_hex(proof_data['publicKey'], 66):
            return False, "Invalid public key"
        if not ADDRESS_RE.match(proof_data['paymentAddr']):
            return False, "Invalid seller payment address"
        if proof_data.get('feeAddr') and not ADDRESS_RE.match(proof_data['feeAddr']):
            return False, "Invalid fee address"
        if not isinstance(proof_data['data'], list) or len(proof_data['data']) != 1:
            return False, "Fixed-price listings must contain exactly one proof entry"

        bid = proof_data['data'][0]
        bid_required = ['price', 'lockTime', 'signature']
        if not all(k in bid for k in bid_required):
            return False, "Missing fixed-price proof entry fields"
        if not isinstance(bid['price'], int) or bid['price'] <= 0:
            return False, "Invalid fixed price"
        if not isinstance(bid['lockTime'], int) or bid['lockTime'] < 0:
            return False, "Invalid lock time"
        if not _is_hex(bid['signature'], 130):
            return False, "Invalid proof signature"
        if 'fee' in bid and (not isinstance(bid['fee'], int) or bid['fee'] < 0):
            return False, "Invalid fee"

        return True, "Valid"
    except Exception as e:
        return False, str(e)

def fixed_price_listing_fields(proof_data: dict) -> dict:
    bid = proof_data['data'][0]
    return {
        'name': proof_data['name'],
        'price_hns': Decimal(bid['price']) / HNS_BASE_UNITS,
        'seller_hns_address': proof_data['paymentAddr'],
        'expires_at': None,
    }
