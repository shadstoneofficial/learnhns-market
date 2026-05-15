from datetime import datetime
from decimal import Decimal

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.exc import IntegrityError

from app.auth import (
    account_limit,
    clear_session_cookie,
    current_account,
    gfavip_authorize_url,
    login_required,
    logout_current_session,
    redirect_with_session,
    upsert_account_from_gfavip,
    validate_gfavip_token,
)
from app.mailgun import send_mailgun_email
from app.models import (
    Account,
    AccountAlertPreference,
    AccountWatchlistItem,
    ExpiringNameWatch,
    GlobalNameState,
    db,
)

account_bp = Blueprint('account', __name__)


@account_bp.route('/auth/gfavip/login')
def gfavip_login():
    return redirect(gfavip_authorize_url(request.args.get('next')))


@account_bp.route('/auth/gfavip/callback')
def gfavip_callback():
    token = request.args.get('token')
    next_url = request.args.get('next') or url_for('account.watchlist_page')
    if not token:
        return render_template('account_error.html', message='GFAVIP did not return a login token.'), 400

    try:
        user = validate_gfavip_token(token)
        account = upsert_account_from_gfavip(user)
    except Exception as exc:
        current_app.logger.warning('GFAVIP login failed: %s', exc)
        return render_template('account_error.html', message='GFAVIP login could not be validated.'), 401

    return redirect_with_session(account, next_url)


@account_bp.route('/auth/logout', methods=['POST'])
def logout():
    logout_current_session()
    response = redirect(url_for('main.index'))
    return clear_session_cookie(response)


@account_bp.route('/account')
@account_bp.route('/account/watchlist')
@login_required
def watchlist_page():
    account = current_account()
    return render_template(
        'account_watchlist.html',
        account=account,
        watchlist_items=[_watchlist_payload(item) for item in _watchlist_query(account).all()],
        watchlist_limit=account_limit(account),
    )


@account_bp.route('/account/alerts')
@login_required
def alerts_page():
    account = current_account()
    prefs = _alert_preferences(account)
    return render_template(
        'account_alerts.html',
        account=account,
        prefs=_alert_preferences_payload(prefs),
        watchlist_count=_watchlist_query(account).count(),
    )


@account_bp.route('/account/settings')
@login_required
def settings_page():
    account = current_account()
    return render_template(
        'account_settings.html',
        account=account,
        watchlist_limit=account_limit(account),
        watchlist_count=_watchlist_query(account).count(),
        prefs=_alert_preferences_payload(_alert_preferences(account)),
    )


@account_bp.route('/alerts/unsubscribe/<token>')
def unsubscribe_alerts(token):
    account = _account_from_manage_token(token)
    if not account:
        return render_template('account_error.html', message='This alert management link is invalid.'), 404

    prefs = _alert_preferences(account)
    prefs.email_enabled = False
    prefs.unsubscribed_at = datetime.utcnow()
    db.session.commit()
    return render_template('account_unsubscribed.html', account=account)


@account_bp.route('/alerts/manage/<token>')
def manage_alerts(token):
    account = _account_from_manage_token(token)
    if not account:
        return render_template('account_error.html', message='This alert management link is invalid.'), 404
    return render_template(
        'account_alerts.html',
        account=account,
        prefs=_alert_preferences_payload(_alert_preferences(account)),
        watchlist_count=_watchlist_query(account).count(),
        manage_token=token,
    )


@account_bp.route('/api/v2/account/me')
def api_me():
    account = current_account()
    if not account:
        return jsonify({'authenticated': False})
    return jsonify({'authenticated': True, 'account': _account_payload(account)})


@account_bp.route('/api/v2/account/watchlist', methods=['GET'])
@login_required
def api_watchlist():
    account = current_account()
    return jsonify({
        'items': [_watchlist_payload(item) for item in _watchlist_query(account).all()],
        'limit': account_limit(account),
    })


@account_bp.route('/api/v2/account/watchlist', methods=['POST'])
@login_required
def api_add_watchlist_item():
    account = current_account()
    data = request.get_json(silent=True) or {}
    name, error = _normalize_name(data.get('name'))
    if error:
        return jsonify({'error': error}), 400

    existing = AccountWatchlistItem.query.filter_by(account_id=account.id, network='main', name=name).first()
    if not existing and _watchlist_query(account).count() >= account_limit(account):
        return jsonify({
            'error': 'Watchlist limit reached',
            'limit': account_limit(account),
        }), 403

    item = existing or AccountWatchlistItem(account=account, name=name, network='main')
    item.alerts_enabled = bool(data.get('alertsEnabled', item.alerts_enabled))
    item.note = data.get('note', item.note)
    if data.get('tags') is not None:
        item.tags_json = data.get('tags') if isinstance(data.get('tags'), list) else []

    db.session.add(item)
    _ensure_public_watch(name, source='account-watch')
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        item = AccountWatchlistItem.query.filter_by(account_id=account.id, network='main', name=name).first()

    return jsonify({'ok': True, 'item': _watchlist_payload(item)})


@account_bp.route('/api/v2/account/watchlist/<name>', methods=['PATCH'])
@login_required
def api_update_watchlist_item(name):
    account = current_account()
    normalized, error = _normalize_name(name)
    if error:
        return jsonify({'error': error}), 400
    item = AccountWatchlistItem.query.filter_by(account_id=account.id, network='main', name=normalized).first_or_404()
    data = request.get_json(silent=True) or {}
    if 'alertsEnabled' in data:
        item.alerts_enabled = bool(data['alertsEnabled'])
    if 'note' in data:
        item.note = data.get('note') or None
    if 'tags' in data:
        item.tags_json = data.get('tags') if isinstance(data.get('tags'), list) else []
    db.session.commit()
    return jsonify({'ok': True, 'item': _watchlist_payload(item)})


@account_bp.route('/api/v2/account/watchlist/<name>', methods=['DELETE'])
@login_required
def api_delete_watchlist_item(name):
    account = current_account()
    normalized, error = _normalize_name(name)
    if error:
        return jsonify({'error': error}), 400
    item = AccountWatchlistItem.query.filter_by(account_id=account.id, network='main', name=normalized).first_or_404()
    db.session.delete(item)
    db.session.commit()
    return jsonify({'ok': True})


@account_bp.route('/api/v2/account/alert-preferences', methods=['GET'])
@login_required
def api_get_alert_preferences():
    return jsonify({'preferences': _alert_preferences_payload(_alert_preferences(current_account()))})


@account_bp.route('/api/v2/account/alert-preferences', methods=['PATCH'])
def api_update_alert_preferences():
    data = request.get_json(silent=True) or {}
    account = current_account()
    if not account and data.get('manageToken'):
        account = _account_from_manage_token(data.get('manageToken'))
    if not account:
        return jsonify({'error': 'Authentication required'}), 401

    prefs = _alert_preferences(account)
    if 'emailEnabled' in data:
        prefs.email_enabled = bool(data['emailEnabled'])
        if prefs.email_enabled:
            prefs.unsubscribed_at = None
    if 'digestEnabled' in data:
        prefs.digest_enabled = bool(data['digestEnabled'])
    if 'reminderDays' in data:
        days = _clean_reminder_days(data['reminderDays'])
        if not days:
            return jsonify({'error': 'Choose at least one reminder day'}), 400
        prefs.reminder_days_json = days
    if 'timezone' in data:
        prefs.timezone = str(data['timezone'] or 'UTC')[:80]
    db.session.commit()
    return jsonify({'ok': True, 'preferences': _alert_preferences_payload(prefs)})


@account_bp.route('/api/v2/account/alerts/test', methods=['POST'])
@login_required
def api_send_test_alert():
    account = current_account()
    if not account.email:
        return jsonify({'error': 'Account has no email address'}), 400
    item = _watchlist_query(account).first()
    name = item.name if item else 'example'
    manage_url = _manage_url(account)
    text = (
        f'This is a LearnHNS renewal alert test for {name}/.\n\n'
        f'Manage alerts: {manage_url}\n'
    )
    result = send_mailgun_email(
        account.email,
        'LearnHNS renewal alert test',
        text,
        variables={'account_id': account.id, 'name': name, 'alert_type': 'test'},
    )
    return jsonify({'ok': True, 'mailgun': result})


def _account_payload(account):
    return {
        'email': account.email,
        'username': account.username,
        'gfavipTier': account.gfavip_tier,
        'localTier': account.local_tier,
        'limits': {'watchlistMax': account_limit(account)},
    }


def _watchlist_query(account):
    return (
        AccountWatchlistItem.query
        .filter_by(account_id=account.id, network='main')
        .order_by(AccountWatchlistItem.created_at.desc())
    )


def _watchlist_payload(item):
    state = _latest_expiring_state(item.name, item.network)
    return {
        'id': item.id,
        'name': item.name,
        'network': item.network,
        'source': item.source,
        'alertsEnabled': item.alerts_enabled,
        'note': item.note,
        'tags': item.tags_json or [],
        'createdAt': item.created_at.isoformat() if item.created_at else None,
        'updatedAt': item.updated_at.isoformat() if item.updated_at else None,
        'expiration': state,
    }


def _latest_expiring_state(name, network='main'):
    global_row = GlobalNameState.query.filter_by(name=name, network=network).first()
    watch_row = ExpiringNameWatch.query.filter_by(name=name, network=network).first()
    candidates = [row for row in (global_row, watch_row) if row]
    if not candidates:
        return {'status': 'pending-refresh'}
    row = max(candidates, key=lambda item: item.last_checked_at or item.updated_at or item.created_at or datetime.min)
    return {
        'status': row.state or ('found' if getattr(row, 'found', True) else 'not-found'),
        'renewalHeight': row.renewal_height,
        'expirationHeight': row.expiration_height,
        'blocksUntilExpire': row.blocks_until_expire,
        'daysUntilExpire': _json_number(row.days_until_expire),
        'hoursUntilExpire': _json_number(row.hours_until_expire),
        'expired': row.expired,
        'sourceHeight': row.source_height,
        'lastCheckedAt': row.last_checked_at.isoformat() if row.last_checked_at else None,
    }


def _json_number(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _ensure_public_watch(name, source='account-watch'):
    watch = ExpiringNameWatch.query.filter_by(name=name, network='main').first()
    if not watch:
        db.session.add(ExpiringNameWatch(name=name, network='main', source=source))


def _normalize_name(raw_name):
    name = str(raw_name or '').strip().lower().rstrip('/')
    if not name:
        return None, 'Name is required'
    if len(name) > 255:
        return None, 'Name is too long'
    if any(char.isspace() for char in name):
        return None, 'Name cannot contain whitespace'
    return name, None


def _alert_preferences(account):
    prefs = account.alert_preferences
    if not prefs:
        prefs = AccountAlertPreference(account=account)
        db.session.add(prefs)
        db.session.commit()
    return prefs


def _alert_preferences_payload(prefs):
    return {
        'emailEnabled': prefs.email_enabled and not bool(prefs.unsubscribed_at),
        'digestEnabled': prefs.digest_enabled,
        'reminderDays': prefs.reminder_days_json or [30, 14, 7, 1],
        'timezone': prefs.timezone,
        'unsubscribedAt': prefs.unsubscribed_at.isoformat() if prefs.unsubscribed_at else None,
    }


def _clean_reminder_days(raw_days):
    if not isinstance(raw_days, list):
        return []
    days = []
    for value in raw_days:
        try:
            day = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= day <= 365 and day not in days:
            days.append(day)
    return sorted(days, reverse=True)


def _manage_serializer():
    return URLSafeSerializer(current_app.config['SECRET_KEY'], salt='learnhns-alerts')


def _manage_token(account):
    return _manage_serializer().dumps({'account_id': account.id})


def _manage_url(account):
    return f"{current_app.config['ALERTS_BASE_URL']}/alerts/manage/{_manage_token(account)}"


def _account_from_manage_token(token):
    try:
        data = _manage_serializer().loads(token)
    except BadSignature:
        return None
    account_id = data.get('account_id')
    if not account_id:
        return None
    return Account.query.get(account_id)
