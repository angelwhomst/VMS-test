import aioodbc


# Connection credentials for the database
server = 'LAPTOP-SSFC864F'  
database_name = 'VMS'
username = 'sa'
password = '2mbrII97'
driver = 'ODBC Driver 17 for SQL Server'


# Function to debug connection
async def test_connection():
    dsn = f"DRIVER={driver};SERVER={server};DATABASE={database_name};UID={username};PWD={password}"
    try:
        print(f"Attempting connection to: {dsn}")
        conn = await aioodbc.connect(dsn=dsn, autocommit=True)
        print("Connection Successful!")
        await conn.close()
    except Exception as e:
        print(f"Connection failed: {e}")


# Function to connect to DB
async def get_db_connection():
    dsn = f"DRIVER={driver};SERVER={server};DATABASE={database_name};UID={username};PWD={password}"
    try:
        conn = await aioodbc.connect(dsn=dsn, autocommit=True)
        return conn
    except Exception as e:
        print(f"Error establishing database connection: {e}")
        raise