from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from dotenv import load_dotenv
import os

# Conexion DataBase
load_dotenv()

# Leer y adaptar URL para driver asíncrono
async_db_url = os.getenv("DATABASE_URL") or ""

engine = create_async_engine(async_db_url, future=True)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

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
