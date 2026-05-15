#!/usr/bin/env python3
import argparse
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import current_app

from app import create_app
from app.mailgun import send_mailgun_email
from app.models import (
    AccountAlertEvent,
    AccountAlertPreference,
    AccountWatchlistItem,
    ExpiringNameWatch,
    GlobalNameState,
    db,
)


def latest_expiring_state(name, network='main'):
    global_row = GlobalNameState.query.filter_by(name=name, network=network).first()
    watch_row = ExpiringNameWatch.query.filter_by(name=name, network=network).first()
    candidates = [row for row in (global_row, watch_row) if row and row.expiration_height]
    if not candidates:
        return None
    return max(candidates, key=lambda row: row.last_checked_at or row.updated_at or row.created_at or datetime.min)


def as_float(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def due_cadence(days_until_expire, reminder_days):
    if days_until_expire is None:
        return None
    try:
        days = float(days_until_expire)
    except (TypeError, ValueError):
        return None
    for cadence in sorted(reminder_days):
        if days <= cadence:
            return cadence
    return None


def already_sent(account_id, item_id, cadence, expiration_height):
    return AccountAlertEvent.query.filter_by(
        account_id=account_id,
        watchlist_item_id=item_id,
        alert_type='renewal-reminder',
        cadence_days=cadence,
        expiration_height=expiration_height,
    ).first()


def alert_body(item, state, cadence, base_url, manage_url, unsubscribe_url):
    days = as_float(state.days_until_expire)
    return (
        f'Renewal reminder for {item.name}/\n\n'
        f'{item.name}/ is within the {cadence}-day reminder window.\n'
        f'Days until expiry: {days if days is not None else "unknown"}\n'
        f'Blocks until expiry: {state.blocks_until_expire if state.blocks_until_expire is not None else "unknown"}\n'
        f'Expiration height: {state.expiration_height if state.expiration_height is not None else "unknown"}\n\n'
        f'Open watchlist: {base_url}/account/watchlist\n'
        f'Manage alerts: {manage_url}\n'
        f'Unsubscribe: {unsubscribe_url}\n\n'
        'LearnHNS sends reminders only. Renew names from your self-custody wallet.'
    )


def send_due_alerts(limit=500, dry_run=False):
    sent = 0
    skipped = 0
    errors = 0
    candidates = (
        AccountWatchlistItem.query
        .filter_by(alerts_enabled=True)
        .order_by(AccountWatchlistItem.created_at.asc())
        .limit(limit)
        .all()
    )

    from app.blueprints.account import _manage_token

    for item in candidates:
        account = item.account
        prefs = account.alert_preferences
        if not prefs:
            prefs = AccountAlertPreference(account=account)
            db.session.add(prefs)
            db.session.commit()
        if not account.email or not prefs.email_enabled or prefs.unsubscribed_at:
            skipped += 1
            continue

        state = latest_expiring_state(item.name, item.network)
        if not state or state.expired:
            skipped += 1
            continue

        cadence = due_cadence(state.days_until_expire, prefs.reminder_days_json or [30, 14, 7, 1])
        if not cadence or already_sent(account.id, item.id, cadence, state.expiration_height):
            skipped += 1
            continue

        token = _manage_token(account)
        base_url = current_app.config['ALERTS_BASE_URL']
        manage_url = f'{base_url}/alerts/manage/{token}'
        unsubscribe_url = f'{base_url}/alerts/unsubscribe/{token}'
        text = alert_body(item, state, cadence, base_url, manage_url, unsubscribe_url)

        if dry_run:
            print(f'[dry-run] would send {cadence}-day alert for {item.name}/ to {account.email}')
            sent += 1
            continue

        event = AccountAlertEvent(
            account_id=account.id,
            watchlist_item_id=item.id,
            name=item.name,
            network=item.network,
            alert_type='renewal-reminder',
            cadence_days=cadence,
            expiration_height=state.expiration_height,
            blocks_until_expire=state.blocks_until_expire,
            days_until_expire=state.days_until_expire,
            status='pending',
        )
        db.session.add(event)
        db.session.flush()
        try:
            result = send_mailgun_email(
                account.email,
                f'Renewal reminder: {item.name}/ expires soon',
                text,
                variables={
                    'account_id': account.id,
                    'watchlist_item_id': item.id,
                    'name': item.name,
                    'alert_type': 'renewal-reminder',
                    'expiration_height': state.expiration_height,
                },
            )
            event.mailgun_message_id = result.get('id')
            event.status = 'sent'
            event.sent_at = datetime.utcnow()
            sent += 1
        except Exception as exc:
            event.status = 'error'
            event.error = str(exc)
            errors += 1
        db.session.commit()

    return {'sent': sent, 'skipped': skipped, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description='Send LearnHNS renewal alert emails for watched names.')
    parser.add_argument('--limit', type=int, default=500)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        result = send_due_alerts(limit=args.limit, dry_run=args.dry_run)
        print(result)


if __name__ == '__main__':
    main()
