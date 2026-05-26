from sqlalchemy import distinct, func

from app.models import AccountWatchlistItem


def watcher_counts_for_names(names, network='main'):
    normalized = sorted({
        str(name or '').strip().lower().rstrip('/')
        for name in names
        if str(name or '').strip()
    })
    if not normalized:
        return {}

    rows = (
        AccountWatchlistItem.query
        .with_entities(
            AccountWatchlistItem.name,
            func.count(distinct(AccountWatchlistItem.account_id)),
        )
        .filter(
            AccountWatchlistItem.network == network,
            AccountWatchlistItem.name.in_(normalized),
        )
        .group_by(AccountWatchlistItem.name)
        .all()
    )
    counts = {name: int(count or 0) for name, count in rows}
    return {name: counts.get(name, 0) for name in normalized}


def watcher_count_for_name(name, network='main'):
    return watcher_counts_for_names([name], network=network).get(
        str(name or '').strip().lower().rstrip('/'),
        0,
    )


def top_watched_names(limit=10, network='main', names=None):
    query = (
        AccountWatchlistItem.query
        .with_entities(
            AccountWatchlistItem.name,
            func.count(distinct(AccountWatchlistItem.account_id)).label('watcher_count'),
        )
        .filter(AccountWatchlistItem.network == network)
    )
    if names is not None:
        normalized = sorted({
            str(name or '').strip().lower().rstrip('/')
            for name in names
            if str(name or '').strip()
        })
        if not normalized:
            return []
        query = query.filter(AccountWatchlistItem.name.in_(normalized))

    rows = (
        query
        .group_by(AccountWatchlistItem.name)
        .order_by(func.count(distinct(AccountWatchlistItem.account_id)).desc(), AccountWatchlistItem.name.asc())
        .limit(limit)
        .all()
    )
    return [{'name': name, 'watcherCount': int(count or 0)} for name, count in rows]


def total_watcher_count(network='main'):
    count = (
        AccountWatchlistItem.query
        .filter(AccountWatchlistItem.network == network)
        .with_entities(func.count(AccountWatchlistItem.id))
        .scalar()
    )
    return int(count or 0)


def watched_name_count(network='main'):
    count = (
        AccountWatchlistItem.query
        .filter(AccountWatchlistItem.network == network)
        .with_entities(func.count(distinct(AccountWatchlistItem.name)))
        .scalar()
    )
    return int(count or 0)
