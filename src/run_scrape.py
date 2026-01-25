# run_scape.py
from db import get_connection, insert_retailer, insert_product, insert_price
from scraper import scrape_products

def run_scrape():
    conn = get_connection()
    try:
        retailer_id = insert_retailer(conn, "Coolblue", "https://coolblue.nl")

        products = scrape_products()

        for product in products:
            print(f"Processing {product['sku']}")
            product_id = insert_product(
                conn,
                retailer_id,
                product["sku"],
                product["brand"],
                product["name"],
                product["url"],
            )

            insert_price(
                conn,
                product_id,
                product["price"],
                product["available"],
            )

        # commit outside the loop
        conn.commit()
        #print("OK, retailer_id:", retailer_id)
        #print("OK, product_id:", product_id)
        #print("OK, price inserted")       

    except Exception as e:
        conn.rollback()
        raise
    
    finally:
        conn.close()

if __name__ == "__main__":
    run_scrape()