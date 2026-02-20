from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection

def test_connection():
    """
    Test the connection to the database and print the server version.
    """
    try:
        # Attempt to connect to the database using get_connection()
        conn = get_connection()
        cur = conn.cursor()

        # Execute a simple SQL query to check the connection
        cur.execute("SELECT current_database(), current_user, inet_server_addr(), inet_server_port();")
        print("Connected to:", cur.fetchone())

        cur.execute("SELECT * FROM retailers LIMIT 1")
        print("Results:", cur.fetchall())

    except Exception as e:
        # Print an error message if something goes wrong
            print("Connection failed:", e)

    finally:
        # Clean up: close the cursor and connection if they were opened
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    # Run the test_connection function if the script is executed directly
    test_connection()