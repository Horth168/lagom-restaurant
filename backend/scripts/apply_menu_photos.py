"""Add the demo menu photos to an existing database (only where a product has no photo yet).

    python -m scripts.apply_menu_photos
"""
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Product


def main() -> int:
    photos = json.loads(Path(__file__).with_name("menu_photos.json").read_text(encoding="utf-8"))
    updated = 0
    with SessionLocal() as db:
        for name, p in photos.items():
            product = db.scalar(select(Product).where(Product.name_en == name))
            if product and not product.image_url:
                product.image_url = p["image_url"]
                product.image_credit = p["image_credit"]
                product.image_source_url = p["image_source_url"]
                updated += 1
        db.commit()
    print(f"Added photos to {updated} products.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
