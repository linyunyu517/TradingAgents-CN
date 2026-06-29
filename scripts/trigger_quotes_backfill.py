import asyncio
import os
import sys

# Ensure repository root is on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, REPO_ROOT)

from app.core.database import close_database, init_database
from app.services.quotes_ingestion_service import QuotesIngestionService


async def main():
    await init_database()
    svc = QuotesIngestionService()
    await svc.ensure_indexes()
    await svc.backfill_last_close_snapshot()
    await close_database()


if __name__ == "__main__":
    asyncio.run(main())
