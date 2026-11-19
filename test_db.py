
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

database_url = os.getenv("DATABASE_URL")

try:
    engine = create_engine(database_url)

    with engine.connect() as connection:
        result = connection.execute(text("SELECT version()"))
        print("Database connected successfully!")
        print(result.scalar())

except Exception as e:
    print("Database connection failed!")
    print(str(e))
