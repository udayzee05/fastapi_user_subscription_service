from pymongo import MongoClient

def download_database(source_uri, db_name):
    """
    Connects to the source MongoDB and retrieves all collections and documents.
    Returns the data as a dictionary.
    """
    print(f"Connecting to source database: {db_name}...")
    source_client = MongoClient(source_uri)
    source_db = source_client[db_name]
    
    database_dump = {}
    try:
        for collection_name in source_db.list_collection_names():
            collection = source_db[collection_name]
            documents = list(collection.find())
            print(f"Downloaded {len(documents)} documents from '{collection_name}'.")
            database_dump[collection_name] = documents

        if not database_dump:
            print("No collections found in the source database.")
    except Exception as e:
        print(f"Error during download: {e}")
    finally:
        source_client.close()
        print("Source database connection closed.")

    return database_dump

def upload_database(target_uri, target_db_name, database_dump):
    """
    Connects to the target MongoDB and uploads the data to the renamed database.
    """
    print(f"Connecting to target database: {target_db_name}...")
    target_client = MongoClient(target_uri)
    target_db = target_client[target_db_name]

    try:
        for collection_name, documents in database_dump.items():
            if documents:
                print(f"Uploading {len(documents)} documents to '{collection_name}'...")
                target_db[collection_name].drop()  # Drop collection if it exists
                target_db[collection_name].insert_many(documents)
                print(f"Successfully uploaded '{collection_name}'.")
            else:
                print(f"Skipping '{collection_name}', no documents to upload.")
    except Exception as e:
        print(f"Error during upload: {e}")
    finally:
        target_client.close()
        print("Target database connection closed.")

if __name__ == "__main__":
    # MongoDB URIs
    source_uri = "mongodb://localhost:27017/testapp"
    target_uri = "mongodb+srv://PlatformAdmin:rSMjxoSPnRf2Rqr2@platform.qxorr.mongodb.net"

    # Source and target database names
    source_db_name = "testapp"  # Old database name
    target_db_name = "platform"  # New database name

    # Step 1: Download the database from the source
    print("Starting database download...")
    database_dump = download_database(source_uri, source_db_name)

    # Step 2: Upload the database to the target with the new name
    if database_dump:
        print("Starting database upload...")
        upload_database(target_uri, target_db_name, database_dump)
        print("Database transfer completed successfully.")
    else:
        print("No data found to upload. Transfer aborted.")
