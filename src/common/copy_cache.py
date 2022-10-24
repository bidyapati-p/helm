import argparse
import os

from common.cache import _MongoKeyValueStore, get_all_sqlite_items
from common.hierarchical_logger import hlog, htrack
from typing import Optional


_SQLITE_FILE_SUFFIX = ".sqlite"


@htrack("Copying all caches")
def copy_all_caches(cache_dir: str, mongo_host: str, bulk_write: bool, dry_run: bool):
    hlog(f"Opening Sqlite dir {cache_dir}")
    with os.scandir(cache_dir) as it:
        for entry in it:
            if entry.name.endswith(_SQLITE_FILE_SUFFIX) and entry.is_file():
                organization = entry.name[: -len(_SQLITE_FILE_SUFFIX)]
                copy_cache(
                    cache_dir=cache_dir,
                    mongo_host=mongo_host,
                    organization=organization,
                    bulk_write=bulk_write,
                    dry_run=dry_run,
                )


@htrack("Copying single cache")
def copy_cache(
    cache_dir: str,
    mongo_host: str,
    organization: str,
    bulk_write: bool,
    dry_run: bool,
    range_start: Optional[int] = None,
    range_end: Optional[int] = None,
):
    if dry_run:
        hlog("Dry run mode, skipping writing to mongo")
    if range_start:
        hlog(f"Start of range: {range_start}")
    if range_end:
        hlog(f"End of range: {range_end}")
    num_items = 0
    num_written = 0
    num_skipped = 0
    num_failed = 0
    cache_path = os.path.join(cache_dir, f"{organization}.sqlite")
    with _MongoKeyValueStore(mongo_host, collection_name=organization) as target_cache:
        bulk_write_pairs = []
        hlog(f"Opening Sqlite cache {cache_path}")
        for key, value in get_all_sqlite_items(cache_path):
            if not dry_run and (not range_start or num_items >= range_start):
                if bulk_write:
                    bulk_write_pairs.append((key, value))
                else:
                    try:
                        target_cache.put(key, value)
                        num_written += 1
                    except Exception as e:
                        hlog(e)
                        num_failed += 1
            else:
                num_skipped += 1
            num_items += 1
            if num_items % 1000 == 0:
                if bulk_write and len(bulk_write_pairs):
                    try:
                        target_cache.multi_put(bulk_write_pairs)
                        hlog(f"Bulk wrote {len(bulk_write_pairs)} items")
                        num_written += len(bulk_write_pairs)
                    except Exception:
                        hlog(f"Bulk write failed {len(bulk_write_pairs)} items")
                        num_failed += len(bulk_write_pairs)
                    bulk_write_pairs = []
                hlog(f"Processed {num_items} items so far")
                hlog(
                    f"Copied {num_written} and skipped {num_skipped} and "
                    + f"failed {num_failed} items from {cache_path} so far"
                )
            if range_end and num_items >= range_end:
                break

        if bulk_write and len(bulk_write_pairs):
            try:
                target_cache.multi_put(bulk_write_pairs)
                hlog(f"Bulk wrote {len(bulk_write_pairs)} items")
                num_written += len(bulk_write_pairs)
            except Exception:
                hlog(f"Bulk write failed {len(bulk_write_pairs)} items")
                num_failed += len(bulk_write_pairs)
            bulk_write_pairs = []
        hlog(f"Processed {num_items} total items from {cache_path}")
        hlog(f"Copied {num_written} and skipped {num_skipped} and failed {num_failed} total items from {cache_path}")
    hlog(f"Finished with Sqlite cache {cache_path}")


def main():
    parser = argparse.ArgumentParser(description="Copy items from Sqlite to mongo")
    parser.add_argument("cache_dir", type=str, help="Directory for the .sqlite files")
    parser.add_argument("mongo_host", type=str, help="Mongo host to copy items to")
    parser.add_argument("--organization", type=str, help="Organization to copy cache for")
    parser.add_argument("--range-start", type=int, help="The start of the range to copy")
    parser.add_argument("--range-end", type=int, help="The end of the range to copy (exclusive)")
    parser.add_argument(
        "--all",
        action="store_true",
        default=None,
        help="Copy caches for all organizations",
    )
    parser.add_argument(
        "--bulk-write",
        action="store_true",
        default=None,
        help="Uses bulk writes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Skips actually writing to mongo",
    )
    args = parser.parse_args()

    if (args.range_start or args.range_end) and not args.organization:
        raise ValueError("--range_start and --range_end require --organization to be specified")

    if args.all:
        copy_all_caches(
            cache_dir=args.cache_dir,
            mongo_host=args.mongo_host,
            bulk_write=bool(args.bulk_write),
            dry_run=bool(args.dry_run),
        )
    elif args.organization:
        copy_cache(
            cache_dir=args.cache_dir,
            mongo_host=args.mongo_host,
            organization=args.organization,
            bulk_write=bool(args.bulk_write),
            dry_run=bool(args.dry_run),
            range_start=args.range_start,
            range_end=args.range_end,
        )
    else:
        raise ValueError("Either --all or --organization must be specified")


if __name__ == "__main__":
    main()
