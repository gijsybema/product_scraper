"""
Script to discover all products from a Coolblue category.
This script runs once a week to check all unique products.

Usage:
    python scripts/discover_products.py [category_url]
    
Example:
    python scripts/discover_products.py "https://www.coolblue.nl/hoofdtelefoons/filter"
"""

import sys
import json
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.coolblue_discovery import get_all_coolblue_products


def main():
    # Get category URL from command line argument or use default
    if len(sys.argv) > 1:
        category_url = sys.argv[1]
    else:
        # Default example category
        category_url = "https://www.coolblue.nl/hoofdtelefoons/filter"
        print(f"No category URL provided, using default: {category_url}")
    
    print(f"Discovering products from: {category_url}")
    print("This may take a while...")
    
    # Get all products
    products = get_all_coolblue_products(category_url)
    
    print(f"Found {len(products)} unique products")
    
    # Ensure data directory exists
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    
    # Write to products.json
    output_file = data_dir / "products.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    
    print(f"Products saved to: {output_file}")


if __name__ == "__main__":
    main()

