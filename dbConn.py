from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from dotenv import load_dotenv
import os

# Conexion DataBase
load_dotenv()

# Leer y adaptar URL para driver asíncrono
async_db_url = os.getenv("DATABASE_URL") or ""

engine = create_async_engine(
    async_db_url,
    future=True,
    echo=True,
)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
  
# Set a per-connection statement timeout to avoid long-hanging queries (PostgreSQL)
from sqlalchemy import event

@event.listens_for(engine.sync_engine, "connect")
def set_statement_timeout(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        # 5000 ms timeout
        cursor.execute("SET statement_timeout = 5000;")
        cursor.close()
    except Exception:
        pass

#Consulta Inventario x Cliente

async def getProds(userId: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("CALL obtener_datos_productos(:userId)"),
            {"userId": userId},
        )
        rows = result.fetchall()
        productos = [
            {
                "sku": row.Sku,
                "nombre": row.Name,
                "precio": row.FinalPrice,
                "stock": row.Stock,
                "categoria": row.FamilySirett,
                "categoriaWpId": row.idFamWP,
                "image": row.Image,
                "imageName": urlparse(row.Image).path.split("/")[-1]
            }
            for row in rows
        ]
        return productos
