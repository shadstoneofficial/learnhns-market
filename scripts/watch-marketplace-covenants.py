#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from app.marketplace_indexer import index_listing_hashes, scan_market_blocks


def main():
    parser = argparse.ArgumentParser(description="Index marketplace-relevant Handshake TRANSFER and FINALIZE covenants.")
    parser.add_argument("--lookback", type=int, default=720)
    parser.add_argument("--max-blocks", type=int, default=720)
    parser.add_argument("--start-height", type=int)
    parser.add_argument("--end-height", type=int)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        while True:
            hash_results = index_listing_hashes()
            block_result = scan_market_blocks(
                start_height=args.start_height,
                end_height=args.end_height,
                lookback=args.lookback,
                max_blocks=args.max_blocks,
            )
            print(json.dumps({
                "success": True,
                "hashes": hash_results,
                "blocks": block_result,
            }, indent=2, sort_keys=True))

            if args.once:
                break

            args.start_height = None
            args.end_height = None
            args.lookback = max(12, min(args.lookback, 120))
            args.max_blocks = max(12, min(args.max_blocks, 120))
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
