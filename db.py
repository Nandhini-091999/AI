import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

def get_db_url():
    host = os.getenv('MYSQL_HOST')
    port = os.getenv('MYSQL_PORT', '3306')
    user = os.getenv('MYSQL_USER')
    pwd = os.getenv('MYSQL_PASSWORD')
    db = os.getenv('MYSQL_DB')
    if not host or not user or not db:
        return None
    return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"

def get_engine():
    url = get_db_url()
    if not url:
        return None
    engine = create_engine(url, future=True)
    return engine
