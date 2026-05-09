import requests
import bleach
from flask import current_app
import json

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

def validate_shakedex_proof(proof_data: dict) -> tuple[bool, str]:
    try:
        if not all(k in proof_data for k in ['name', 'price', 'lock', 'signatures']):
            return False, "Missing required fields"
        # Add signature / expiration checks here later
        return True, "Valid"
    except Exception as e:
        return False, str(e)
