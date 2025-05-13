from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class Product(BaseModel):
    sku: str = Field(..., description="Identificador único del producto")
    nombre: Optional[str] = Field(None, description="Nombre del producto")
    precio: Optional[float] = Field(None, description="Precio del producto")
    stock: Optional[int] = Field(None, description="Cantidad en inventario")
    categoria: Optional[Any] = Field(None, description="Categoría del producto (WooCommerce)")
    categoriaWpId: Optional[int] = Field(None, description="ID de categoría en WooCommerce")
    image: Optional[str] = Field(None, description="URL de la imagen del producto")
    imageName: Optional[str] = Field(None, description="Nombre del archivo de imagen")

class ItemsResponse(BaseModel):
    client: str = Field(..., description="Cliente consultado")
    provider: str = Field(..., description="Fuente de datos: 'db' o proveedor SOAP")
    count: int = Field(..., description="Número de productos retornados")
    elapsed: float = Field(..., description="Tiempo de ejecución en segundos")
    productos: List[Product] = Field(..., description="Lista de productos")

# Campos permitidos para respuestas SOAP
ALLOWED_SOAP_FIELDS: List[str] = [
    "codigo", "descripcion", "desc_corta", "familia_id", "familia",
    "marca", "clase", "precio", "stock", "image_url",
    "itemref_1", "privacidad"
]
  
class InventoryResponse(BaseModel):
    client: str
    dbId: Optional[int] = None
    count: int
    elapsed: float
    productos: List[Product]

class SoapResponse(BaseModel):
    client: str
    bid: Optional[int] = None
    count: int
    elapsed: float
    data: Any

class MissingWPResponse(BaseModel):
    client: str
    provider: str
    count: int
    elapsed: float
    missingWp: List[str]

class MessageResponse(BaseModel):
    message: str

class PriceListResult(BaseModel):
    priceList: str
    listId: int
    inserted: int
    updated: int
    unchanged: int
    messages: List[str]

class PriceListResponse(BaseModel):
    results: List[PriceListResult]