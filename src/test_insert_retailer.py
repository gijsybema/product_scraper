from db import insert_retailer

if __name__ == "__main__":
    retailer_id = insert_retailer(
        name="Coolblue",
        base_url="https://www.coolblue.nl"
    )
    
    if retailer_id is not None:
        print("Retailer inserted with ID:", retailer_id)
    else:
        print("Retailer not inserted: already exists.")