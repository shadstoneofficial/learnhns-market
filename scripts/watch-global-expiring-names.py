#!/usr/bin/env python3
"""Forward-only Handshake name-state watcher.

This job intentionally starts at the current HSD height and only records names
observed in future blocks. It is not a historical backfill.
"""

import argparse
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
NAME_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
NAME_HASH_COVENANT_ACTIONS = {"CLAIM", "REVEAL", "REGISTER", "RENEW", "FINALIZE"}
NAME_HASH_COVENANT_TYPES = {
    1: "CLAIM",
    4: "REVEAL",
    6: "REGISTER",
    8: "RENEW",
    10: "FINALIZE",
}

create_app = None
db = None
NameIndexerProgress = None
_expiring_name_payload = None
_fetch_hsd_tx = None
_hsd_request = None
_hsd_rpc_request = None
_store_global_name_state = None
get_hsd_status_payload = None


def _load_app_bindings():
    global create_app
    global db
    global NameIndexerProgress
    global _expiring_name_payload
    global _fetch_hsd_tx
    global _hsd_request
    global _hsd_rpc_request
    global _store_global_name_state
    global get_hsd_status_payload

    from app import create_app as app_factory
    from app.blueprints.api import (
        _expiring_name_payload as expiring_name_payload,
        _fetch_hsd_tx as fetch_hsd_tx,
        _hsd_request as hsd_request,
        _hsd_rpc_request as hsd_rpc_request,
        _store_global_name_state as store_global_name_state,
        get_hsd_status_payload as hsd_status_payload,
    )
    from app.models import db as app_db, NameIndexerProgress as indexer_progress_model

    create_app = app_factory
    db = app_db
    NameIndexerProgress = indexer_progress_model
    _expiring_name_payload = expiring_name_payload
    _fetch_hsd_tx = fetch_hsd_tx
    _hsd_request = hsd_request
    _hsd_rpc_request = hsd_rpc_request
    _store_global_name_state = store_global_name_state
    get_hsd_status_payload = hsd_status_payload


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _normalize_name(value):
    if not isinstance(value, str):
        return None

    name = value.strip().lower().rstrip("/")
    if not NAME_RE.match(name):
        return None
    return name


def _decode_covenant_item(value):
    if isinstance(value, dict) and isinstance(value.get("data"), list):
        try:
            value = bytes(value["data"]).hex()
        except (TypeError, ValueError):
            return None

    if not isinstance(value, str):
        return None

    if value.startswith("0x"):
        value = value[2:]

    if len(value) % 2 != 0:
        return None

    try:
        raw = bytes.fromhex(value)
        text = raw.decode("ascii")
    except (ValueError, UnicodeDecodeError):
        return None

    return _normalize_name(text)


def _decode_covenant_item_hex(value):
    if isinstance(value, dict) and isinstance(value.get("data"), list):
        try:
            value = bytes(value["data"]).hex()
        except (TypeError, ValueError):
            return None

    if not isinstance(value, str):
        return None

    value = value.strip().lower()
    if value.startswith("0x"):
        value = value[2:]

    if not NAME_HASH_RE.match(value):
        return None

    return value


def _covenant_action(covenant):
    if not isinstance(covenant, dict):
        return None

    action = covenant.get("action")
    if isinstance(action, str):
        return action.upper()

    covenant_type = covenant.get("type")
    if isinstance(covenant_type, int):
        return NAME_HASH_COVENANT_TYPES.get(covenant_type)

    return None


def _names_from_covenant(covenant):
    if not isinstance(covenant, dict):
        return set()

    names = set()
    for key in ("name", "rawName", "nameString"):
        name = _normalize_name(covenant.get(key))
        if name:
            names.add(name)

    for item in covenant.get("items") or []:
        name = _decode_covenant_item(item)
        if name:
            names.add(name)

    return names


def _name_hashes_from_covenant(covenant):
    if _covenant_action(covenant) not in NAME_HASH_COVENANT_ACTIONS:
        return set()

    items = covenant.get("items") or []
    if not items:
        return set()

    name_hash = _decode_covenant_item_hex(items[0])
    return {name_hash} if name_hash else set()


def _extract_names_from_tx(tx):
    if not isinstance(tx, dict):
        return set()

    names = set()
    sections = []
    for key in ("outputs", "vout", "inputs", "vin"):
        values = tx.get(key)
        if isinstance(values, list):
            sections.extend(values)

    for entry in sections:
        if not isinstance(entry, dict):
            continue
        names.update(_names_from_covenant(entry.get("covenant")))
        script = entry.get("scriptPubKey")
        if isinstance(script, dict):
            names.update(_names_from_covenant(script.get("covenant")))

    return names


def _extract_name_hashes_from_tx(tx):
    if not isinstance(tx, dict):
        return set()

    hashes = set()
    sections = []
    for key in ("outputs", "vout"):
        values = tx.get(key)
        if isinstance(values, list):
            sections.extend(values)

    for entry in sections:
        if not isinstance(entry, dict):
            continue
        hashes.update(_name_hashes_from_covenant(entry.get("covenant")))
        script = entry.get("scriptPubKey")
        if isinstance(script, dict):
            hashes.update(_name_hashes_from_covenant(script.get("covenant")))

    return hashes


def _name_from_hash(name_hash):
    name, error = _hsd_rpc_request("getnamebyhash", [name_hash, True])
    if error or not isinstance(name, str):
        return None
    return _normalize_name(name)


def _get_chain_height():
    payload, status = get_hsd_status_payload()
    if status != 200 or not payload.get("reachable"):
        raise RuntimeError(payload.get("error") or "HSD node is not reachable")

    height = payload.get("height")
    if not isinstance(height, int):
        raise RuntimeError("HSD status did not include a chain height")
    return height


def _get_block_hash(height):
    block_hash, error = _hsd_rpc_request("getblockhash", [height])
    if error:
        raise RuntimeError(f"Could not fetch block hash for height {height}: {error[0]}")
    return block_hash


def _get_block(block_hash):
    attempts = (
        ("rpc-verbose-tx", lambda: _hsd_rpc_request("getblock", [block_hash, True, True])),
        ("rpc-verbose", lambda: _hsd_rpc_request("getblock", [block_hash, True])),
        ("http", lambda: _hsd_request(f"/block/{block_hash}")),
    )

    last_error = None
    for _label, fetcher in attempts:
        block, error = fetcher()
        if not error and isinstance(block, dict):
            return block
        last_error = error

    message = last_error[0] if last_error else "HSD returned a non-JSON block response"
    raise RuntimeError(f"Could not fetch block {block_hash}: {message}")


def _tx_entries(block):
    for key in ("tx", "txs", "transactions"):
        entries = block.get(key)
        if isinstance(entries, list):
            return entries
    return []


def _fetch_tx_if_needed(entry):
    if isinstance(entry, dict):
        return entry
    if isinstance(entry, str):
        tx, error = _fetch_hsd_tx(entry)
        if error:
            return None
        return tx
    return None


def _names_from_block(block):
    names = set()
    name_hashes = set()
    for entry in _tx_entries(block):
        tx = _fetch_tx_if_needed(entry)
        names.update(_extract_names_from_tx(tx))
        name_hashes.update(_extract_name_hashes_from_tx(tx))

    for name_hash in name_hashes:
        name = _name_from_hash(name_hash)
        if name:
            names.add(name)

    return sorted(names)


def _progress_for(network):
    progress = NameIndexerProgress.query.filter_by(network=network).first()
    if progress is None:
        progress = NameIndexerProgress(network=network)
        db.session.add(progress)
    return progress


def _bootstrap(network, height):
    progress = _progress_for(network)
    if progress.last_indexed_height is None:
        now = datetime.utcnow()
        progress.status = "watching"
        progress.last_indexed_height = height
        progress.target_height = height
        progress.last_error = None
        progress.started_at = now
        progress.finished_at = None
        progress.updated_at = now
        db.session.commit()
        return True
    return False


def _record_name(name, height, network, dry_run=False):
    payload = _expiring_name_payload(name, chain_height=height)
    if not payload.get("found"):
        return None
    if not isinstance(payload.get("blocksUntilExpire"), int):
        return None

    if dry_run:
        return payload

    row = _store_global_name_state(payload, chain_height=height, network=network)
    return row


def run_once(network="main", batch_size=10, start_height=None, target_height=None, force_start_height=False, dry_run=False):
    current_height = _get_chain_height()
    target_height = min(target_height, current_height) if target_height is not None else current_height

    if _bootstrap(network, start_height or target_height):
        return {
            "bootstrapped": True,
            "network": network,
            "lastIndexedHeight": start_height or target_height,
            "targetHeight": target_height,
            "blocksProcessed": 0,
            "namesObserved": 0,
            "namesRecorded": 0,
        }

    progress = _progress_for(network)
    if start_height is not None and force_start_height:
        progress.last_indexed_height = start_height - 1
    elif start_height is not None and (progress.last_indexed_height is None or progress.last_indexed_height < start_height - 1):
        progress.last_indexed_height = start_height - 1

    start = (progress.last_indexed_height or 0) + 1
    target = target_height
    end = min(target, start + batch_size - 1)

    if start > target:
        progress.status = "watching"
        progress.target_height = target
        progress.last_error = None
        progress.updated_at = datetime.utcnow()
        if not dry_run:
            db.session.commit()
        return {
            "bootstrapped": False,
            "network": network,
            "lastIndexedHeight": progress.last_indexed_height,
            "targetHeight": target,
            "blocksProcessed": 0,
            "namesObserved": 0,
            "namesRecorded": 0,
        }

    blocks_processed = 0
    names_observed = 0
    names_recorded = 0

    for height in range(start, end + 1):
        block_hash = _get_block_hash(height)
        block = _get_block(block_hash)
        names = _names_from_block(block)
        names_observed += len(names)

        for name in names:
            if _record_name(name, height, network, dry_run=dry_run):
                names_recorded += 1

        progress.last_indexed_height = height
        blocks_processed += 1

    progress.status = "watching" if end >= target else "syncing"
    progress.target_height = target
    progress.names_indexed = (progress.names_indexed or 0) + names_recorded
    progress.last_error = None
    progress.finished_at = datetime.utcnow() if end >= target else None
    progress.updated_at = datetime.utcnow()

    if not dry_run:
        db.session.commit()
    else:
        db.session.rollback()

    return {
        "bootstrapped": False,
        "network": network,
        "lastIndexedHeight": progress.last_indexed_height,
        "targetHeight": target,
        "blocksProcessed": blocks_processed,
        "namesObserved": names_observed,
        "namesRecorded": names_recorded,
        "caughtUp": end >= target,
        "dryRun": dry_run,
    }


def _mark_error(network, exc):
    progress = _progress_for(network)
    progress.status = "error"
    progress.last_error = str(exc)
    progress.updated_at = datetime.utcnow()
    db.session.commit()


def main():
    parser = argparse.ArgumentParser(description="Watch new HSD blocks and record forward-only global name expiry state.")
    parser.add_argument("--network", default="main")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--start-height", type=int)
    parser.add_argument("--target-height", type=int)
    parser.add_argument("--force-start-height", action="store_true", help="Reset stored progress to start-height - 1 before processing.")
    parser.add_argument("--once", action="store_true", help="Run one batch and exit.")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    _load_app_bindings()
    app = create_app()
    with app.app_context():
        while True:
            try:
                result = run_once(
                    network=args.network,
                    batch_size=max(args.batch_size, 1),
                    start_height=args.start_height,
                    target_height=args.target_height,
                    force_start_height=args.force_start_height,
                    dry_run=args.dry_run,
                )
                print(json.dumps(result, indent=2, sort_keys=True, default=_json_default))
            except Exception as exc:  # pragma: no cover - operational guard.
                _mark_error(args.network, exc)
                print(json.dumps({
                    "success": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }, indent=2))
                if args.once:
                    raise

            if args.once:
                break
            args.start_height = None
            time.sleep(max(args.poll_seconds, 5))


if __name__ == "__main__":
    main()
