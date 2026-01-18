from db import insert_price

if __name__ == "__main__":
    insert_price(
        product_id=1,
        price=349.00,
        availability=True
    )

    print("Price inserted")