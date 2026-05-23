import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode

import requests
from flask import current_app, make_response, redirect, request, url_for

from app.models import Account, AccountAlertPreference, AccountSession, db

SESSION_COOKIE = 'learnhns_session'


def token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def current_account():
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        return None

    session = (
        AccountSession.query
        .filter_by(session_token_hash=token_hash(raw_token), revoked_at=None)
        .first()
    )
    if not session or session.expires_at <= datetime.utcnow():
        return None
    return session.account


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        account = current_account()
        if not account:
            next_url = request.full_path if request.query_string else request.path
            if request.path.startswith('/api/'):
                return {'error': 'Authentication required'}, 401
            return redirect(url_for('account.login_page', next=next_url))
        return view(*args, **kwargs)

    return wrapped


def account_limit(account):
    if account and account.local_tier in {'pro', 'team'}:
        return current_app.config['PRO_WATCHLIST_LIMIT']
    return current_app.config['FREE_WATCHLIST_LIMIT']


def gfavip_authorize_url(next_url=None):
    callback_url = current_app.config.get('GFAVIP_SSO_CALLBACK_URL') or url_for(
        'account.gfavip_callback',
        _external=True,
    )
    if next_url:
        separator = '&' if '?' in callback_url else '?'
        callback_url = f'{callback_url}{separator}{urlencode({"next": next_url})}'

    params = urlencode({
        'redirect_uri': callback_url,
        'service': current_app.config['GFAVIP_SSO_SERVICE'],
    })
    return f"{current_app.config['GFAVIP_SSO_BASE_URL']}/api/auth/sso/authorize?{params}"


def validate_gfavip_token(token):
    response = requests.get(
        current_app.config['GFAVIP_SSO_VALIDATE_URL'],
        headers={'Authorization': f'Bearer {token}'},
        timeout=current_app.config['GFAVIP_SSO_TIMEOUT'],
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get('user'):
        payload = payload['user']
    return payload


def upsert_account_from_gfavip(user):
    gfavip_user_id = user.get('id') or user.get('user_id') or user.get('userId')
    if not gfavip_user_id:
        raise ValueError('GFAVIP validation response did not include a user id')

    gfavip_tier = user.get('tier') or 'free'
    local_tier = 'pro' if gfavip_tier in {'paid', 'team'} else 'free'
    account = Account.query.filter_by(gfavip_user_id=str(gfavip_user_id)).first()
    if not account:
        account = Account(gfavip_user_id=str(gfavip_user_id))
        db.session.add(account)

    account.email = user.get('email') or account.email
    account.username = user.get('username') or user.get('name') or account.username
    account.display_name = user.get('displayName') or user.get('display_name') or account.username
    account.gfavip_tier = gfavip_tier
    account.local_tier = local_tier
    account.last_login_at = datetime.utcnow()

    if not account.alert_preferences:
        db.session.add(AccountAlertPreference(account=account))

    db.session.commit()
    return account


def create_account_session(account):
    raw_token = secrets.token_urlsafe(48)
    days = current_app.config['ACCOUNT_SESSION_DAYS']
    session = AccountSession(
        account=account,
        session_token_hash=token_hash(raw_token),
        expires_at=datetime.utcnow() + timedelta(days=days),
    )
    db.session.add(session)
    db.session.commit()
    return raw_token, session.expires_at


def attach_session_cookie(response, raw_token, expires_at):
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        expires=expires_at,
        httponly=True,
        secure=request.is_secure or current_app.config.get('ACCOUNT_COOKIE_SECURE'),
        samesite='Lax',
    )
    return response


def clear_session_cookie(response):
    response.delete_cookie(SESSION_COOKIE)
    return response


def logout_current_session():
    raw_token = request.cookies.get(SESSION_COOKIE)
    if raw_token:
        session = AccountSession.query.filter_by(session_token_hash=token_hash(raw_token)).first()
        if session and not session.revoked_at:
            session.revoked_at = datetime.utcnow()
            db.session.commit()


def redirect_with_session(account, next_url=None):
    raw_token, expires_at = create_account_session(account)
    response = make_response(redirect(next_url or url_for('account.watchlist_page')))
    return attach_session_cookie(response, raw_token, expires_at)
