from datetime import datetime

from app.models import (
    db,
    Listing,
    MarketplaceCovenantEvent,
    MarketplaceIndexerProgress,
    PendingListing,
)
from app.blueprints.api import (
    _fetch_explorer_tx,
    _fetch_hsd_name_info,
    _fetch_hsd_tx,
    _hsd_request,
    _hsd_rpc_request,
    get_hsd_status_payload,
)


MARKETPLACE_COVENANT_ACTIONS = {'TRANSFER', 'FINALIZE'}
NAME_RELEVANT_COVENANT_TYPES = {
    9: 'TRANSFER',
    10: 'FINALIZE',
}


def normalize_name(value):
    if not isinstance(value, str):
        return None
    name = value.strip().lower().rstrip('/')
    return name or None


def covenant_action(covenant):
    if not isinstance(covenant, dict):
        return None

    action = covenant.get('action')
    if isinstance(action, str):
        return action.upper()

    covenant_type = covenant.get('type')
    if isinstance(covenant_type, int):
        return NAME_RELEVANT_COVENANT_TYPES.get(covenant_type)

    return None


def decode_covenant_name_item(value):
    if isinstance(value, dict) and isinstance(value.get('data'), list):
        try:
            value = bytes(value['data']).hex()
        except (TypeError, ValueError):
            return None

    if not isinstance(value, str):
        return None

    value = value.strip().lower()
    if value.startswith('0x'):
        value = value[2:]
    if len(value) % 2 != 0:
        return None

    try:
        return normalize_name(bytes.fromhex(value).decode('ascii'))
    except (ValueError, UnicodeDecodeError):
        return None


def covenant_name(covenant):
    if not isinstance(covenant, dict):
        return None

    for key in ('name', 'rawName', 'nameString'):
        name = normalize_name(covenant.get(key))
        if name:
            return name

    for item in covenant.get('items') or []:
        name = decode_covenant_name_item(item)
        if name:
            return name

    return None


def tx_hash(tx):
    if not isinstance(tx, dict):
        return None
    value = tx.get('txid') or tx.get('id') or tx.get('hash')
    if isinstance(value, str) and len(value) == 64:
        return value.lower()
    return None


def block_time(block, tx=None):
    value = None
    if isinstance(tx, dict):
        value = tx.get('time') or tx.get('mtime')
    if value is None and isinstance(block, dict):
        value = block.get('time') or block.get('mtime')
    if isinstance(value, int):
        return datetime.utcfromtimestamp(value)
    return None


def tx_outputs(tx):
    if not isinstance(tx, dict):
        return []
    for key in ('outputs', 'vout'):
        outputs = tx.get(key)
        if isinstance(outputs, list):
            return outputs
    return []


def output_covenant(output):
    if not isinstance(output, dict):
        return {}
    covenant = output.get('covenant')
    if isinstance(covenant, dict):
        return covenant
    script = output.get('scriptPubKey')
    if isinstance(script, dict) and isinstance(script.get('covenant'), dict):
        return script['covenant']
    return {}


def output_index(output, fallback):
    for key in ('index', 'n'):
        value = output.get(key) if isinstance(output, dict) else None
        if isinstance(value, int):
            return value
    return fallback


def record_event(name, action, tx_hash_value, output_idx, block_height=None, block_hash=None, event_time=None, source='hsd-block', raw=None, network='main'):
    name = normalize_name(name)
    if not name or action not in MARKETPLACE_COVENANT_ACTIONS or not tx_hash_value:
        return None, False

    event = MarketplaceCovenantEvent.query.filter_by(
        network=network,
        tx_hash=tx_hash_value,
        output_index=output_idx,
        covenant_action=action,
        name=name,
    ).first()
    created = event is None
    if event is None:
        event = MarketplaceCovenantEvent(
            network=network,
            tx_hash=tx_hash_value,
            output_index=output_idx,
            covenant_action=action,
            name=name,
        )
        db.session.add(event)

    event.block_height = block_height if block_height is not None else event.block_height
    event.block_hash = block_hash or event.block_hash
    event.block_time = event_time or event.block_time
    event.source = source or event.source
    event.raw_json = raw if raw is not None else event.raw_json
    event.updated_at = datetime.utcnow()
    return event, created


def index_tx(tx, block=None, source='hsd-tx', observed_names=None, network='main'):
    tx_hash_value = tx_hash(tx)
    if not tx_hash_value:
        return 0

    observed = {normalize_name(name) for name in (observed_names or [])}
    observed.discard(None)
    height = tx.get('height') if isinstance(tx.get('height'), int) else None
    if height is None and isinstance(block, dict) and isinstance(block.get('height'), int):
        height = block.get('height')
    hash_value = block.get('hash') if isinstance(block, dict) and isinstance(block.get('hash'), str) else None
    event_time = block_time(block, tx)

    created_count = 0
    for fallback_index, output in enumerate(tx_outputs(tx)):
        covenant = output_covenant(output)
        action = covenant_action(covenant)
        if action not in MARKETPLACE_COVENANT_ACTIONS:
            continue
        name = covenant_name(covenant)
        if observed and name not in observed:
            continue

        _event, created = record_event(
            name=name,
            action=action,
            tx_hash_value=tx_hash_value,
            output_idx=output_index(output, fallback_index),
            block_height=height,
            block_hash=hash_value,
            event_time=event_time,
            source=source,
            raw={
                'txHash': tx_hash_value,
                'output': output,
            },
            network=network,
        )
        if created:
            created_count += 1

    return created_count


def fetch_tx(tx_hash_value):
    tx, error = _fetch_hsd_tx(tx_hash_value)
    if not error and isinstance(tx, dict):
        return tx, 'hsd-tx', None

    tx, explorer_error = _fetch_explorer_tx(tx_hash_value)
    if not explorer_error and isinstance(tx, dict):
        return tx, 'tx-explorer', None

    return None, None, error or explorer_error


def index_tx_hash(tx_hash_value, network='main'):
    tx, source, error = fetch_tx(tx_hash_value)
    if error:
        return {
            'txHash': tx_hash_value,
            'indexed': 0,
            'error': error[0],
        }

    count = index_tx(tx, source=source, network=network)
    db.session.commit()
    return {
        'txHash': tx_hash_value,
        'indexed': count,
        'source': source,
    }


def observed_market_names():
    names = set()
    for listing in Listing.query.all():
        name = normalize_name(listing.name)
        if name:
            names.add(name)
    for pending in PendingListing.query.all():
        name = normalize_name(pending.name)
        if name:
            names.add(name)
    return names


def get_chain_height():
    payload, status = get_hsd_status_payload()
    if status != 200 or not payload.get('reachable'):
        raise RuntimeError(payload.get('error') or 'HSD node is not reachable')
    height = payload.get('height')
    if not isinstance(height, int):
        raise RuntimeError('HSD status did not include a chain height')
    return height


def get_block_hash(height):
    block_hash, error = _hsd_rpc_request('getblockhash', [height])
    if error:
        raise RuntimeError(f'Could not fetch block hash for height {height}: {error[0]}')
    return block_hash


def get_block(block_hash_value):
    attempts = (
        lambda: _hsd_rpc_request('getblock', [block_hash_value, True, True]),
        lambda: _hsd_rpc_request('getblock', [block_hash_value, True]),
        lambda: _hsd_request(f'/block/{block_hash_value}'),
    )
    last_error = None
    for fetcher in attempts:
        block, error = fetcher()
        if not error and isinstance(block, dict):
            return block
        last_error = error
    message = last_error[0] if last_error else 'HSD returned no block'
    raise RuntimeError(f'Could not fetch block {block_hash_value}: {message}')


def block_txs(block):
    for key in ('tx', 'txs', 'transactions'):
        txs = block.get(key) if isinstance(block, dict) else None
        if isinstance(txs, list):
            return txs
    return []


def fetch_tx_if_needed(entry):
    if isinstance(entry, dict):
        return entry
    if isinstance(entry, str):
        tx, _source, _error = fetch_tx(entry)
        return tx
    return None


def progress_for(network='main'):
    progress = MarketplaceIndexerProgress.query.filter_by(network=network).first()
    if progress is None:
        progress = MarketplaceIndexerProgress(network=network, status='not-started', events_indexed=0)
        db.session.add(progress)
    return progress


def scan_market_blocks(start_height=None, end_height=None, lookback=720, network='main', max_blocks=720):
    chain_height = get_chain_height()
    end = min(end_height or chain_height, chain_height)
    start = start_height if start_height is not None else max(0, end - lookback)
    if end < start:
        return {'blocksProcessed': 0, 'eventsIndexed': 0, 'startHeight': start, 'endHeight': end}
    if end - start + 1 > max_blocks:
        start = end - max_blocks + 1

    names = observed_market_names()
    progress = progress_for(network)
    now = datetime.utcnow()
    progress.status = 'running'
    progress.target_height = end
    progress.started_at = now
    progress.last_error = None
    db.session.commit()

    blocks_processed = 0
    events_indexed = 0
    try:
        for height in range(start, end + 1):
            block_hash_value = get_block_hash(height)
            block = get_block(block_hash_value)
            if isinstance(block, dict):
                block.setdefault('height', height)
                block.setdefault('hash', block_hash_value)
            for entry in block_txs(block):
                tx = fetch_tx_if_needed(entry)
                events_indexed += index_tx(tx, block=block, source='hsd-block', observed_names=names, network=network)
            progress.last_indexed_height = height
            blocks_processed += 1
            if blocks_processed % 25 == 0:
                db.session.commit()

        progress.status = 'watching'
        progress.finished_at = datetime.utcnow()
        progress.events_indexed = (progress.events_indexed or 0) + events_indexed
        progress.updated_at = datetime.utcnow()
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        progress = progress_for(network)
        progress.status = 'failed'
        progress.last_error = str(exc)
        progress.updated_at = datetime.utcnow()
        db.session.commit()
        raise

    return {
        'blocksProcessed': blocks_processed,
        'eventsIndexed': events_indexed,
        'startHeight': start,
        'endHeight': end,
        'observedNames': len(names),
    }


def index_listing_hashes(network='main'):
    hashes = set()
    for listing in Listing.query.filter(Listing.status.in_(('sold', 'completed'))).all():
        for value in (listing.transfer_start_tx_hash, listing.sale_tx_hash):
            if isinstance(value, str) and len(value) == 64:
                hashes.add(value.lower())

    results = []
    for tx_hash_value in sorted(hashes):
        results.append(index_tx_hash(tx_hash_value, network=network))
    return results


def event_for_tx(tx_hash_value, name=None, action=None, network='main'):
    if not tx_hash_value:
        return None
    query = MarketplaceCovenantEvent.query.filter_by(network=network, tx_hash=tx_hash_value.lower())
    if name:
        query = query.filter_by(name=normalize_name(name))
    if action:
        query = query.filter_by(covenant_action=action.upper())
    return query.order_by(MarketplaceCovenantEvent.block_height.desc()).first()


def events_for_name(name, network='main'):
    return (
        MarketplaceCovenantEvent.query
        .filter_by(network=network, name=normalize_name(name))
        .order_by(MarketplaceCovenantEvent.block_height.desc(), MarketplaceCovenantEvent.output_index.asc())
        .all()
    )


def name_state(name):
    info, error = _fetch_hsd_name_info(normalize_name(name))
    if error:
        return {'found': False, 'error': error[0]}
    return {'found': True, 'info': info}
