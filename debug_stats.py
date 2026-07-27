"""Debug get_catalog_stats."""
import asyncio
from tests.test_e2e import FakeD1
from src.store.seed import seed_to_d1
from src.store.catalog import get_catalog_stats


async def main():
    db = FakeD1()
    await seed_to_d1(db)
    # Direct test of the aggregate query
    rows = await db.prepare(
        "SELECT niche, status, pricing_vnd, COUNT(*) AS n FROM tools GROUP BY niche, status, pricing_vnd"
    ).all()
    print("Aggregate query result:", rows)
    stats = await get_catalog_stats(db)
    print("Stats:", stats)


asyncio.run(main())
