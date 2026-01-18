from db import insert_product

if __name__ == "__main__":
    product_id = insert_product(
        retailer_id=1,
        sku="SONY-WH1000XM5",
        brand="Sony",
        name="Sony WH-1000XM5",
        product_url="https://example.com/sony-wh1000xm5"
    )

    if product_id is not None:
        print("Product inserted with ID:", product_id)
    else:
        print("Product not inserted: already exists.")