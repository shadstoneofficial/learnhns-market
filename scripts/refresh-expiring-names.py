#!/usr/bin/env python3
import argparse
import json

from app import create_app
from app.blueprints.api import _refresh_expiring_watches


def main():
    parser = argparse.ArgumentParser(description="Refresh channel-observed expiring name watches.")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--all", action="store_true", help="Refresh even recently checked names.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        result = _refresh_expiring_watches(limit=args.limit, stale_only=not args.all)
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
