"""Cliente asincrónico para la API REST de WooCommerce usando httpx."""
import asyncio
import httpx
from typing import Optional

class WooCommerceAPI:

    def __init__(self, url: str, consumer_key: str, consumer_secret: str, timeout: int = 40):
        """
        Inicializa el cliente de la API de WooCommerce.
        url: URL base de la tienda, sin la barra al final
        consumer_key, consumer_secret: credenciales de la API REST
        timeout: tiempo de espera para las peticiones, en segundos
        """
        # Asegura que no haya una barra al final de la URL
        self.base_url = url.rstrip("/")
        self.auth = (consumer_key, consumer_secret)
        self.timeout = timeout

    async def _fetch_with_retries(self, client, url, auth, params, retries=3, delay=1):
        for attempt in range(retries):
            try:
                response = await client.get(url, auth=auth, params=params)
                response.raise_for_status()
                return response
            except httpx.RequestError as e:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(delay)  # backoff lineal

    async def get_all_products(self, per_page: int = 50, delay: float = 0.3, max_pages: Optional[int] = None) -> list:
        """Recupera productos paginadamente con retries y sleep opcional."""
        url = f"{self.base_url}/wp-json/wc/v3/products"
        filtered_data = []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            first_page = await self._fetch_with_retries(client, url, self.auth, {"page": 1, "per_page": per_page})
            raw_data = first_page.json()
            filtered_data.extend(self._filter_products(raw_data))

            total_pages = int(first_page.headers.get("X-WP-TotalPages", 1))
            if max_pages:
                total_pages = min(total_pages, max_pages)

            for page in range(2, total_pages + 1):
                await asyncio.sleep(delay)
                resp = await self._fetch_with_retries(client, url, self.auth, {"page": page, "per_page": per_page})
                raw_data = resp.json()
                filtered_data.extend(self._filter_products(raw_data))

        return filtered_data

    def _filter_products(self, raw_data):
        products = []
        for product in raw_data:
            categoria = (
                {
                    "id": product["categories"][0]["id"],
                    "name": product["categories"][0]["name"]
                }
                if product.get("categories") else None
            )
            imagen = (
                {
                    "src": product["images"][0]["src"],
                    "name": product["images"][0]["name"]
                }
                if product.get("images") else None
            )

            products.append({
                # Include product ID for update operations
                "id": product.get("id"),
                "sku": product.get("sku"),
                "nombre": product.get("name"),
                "precio": product.get("regular_price"),
                "stock": product.get("stock_quantity"),
                "categoria": categoria,
                "imagen": imagen
            })
        return products

    async def update_product(self, product_sku: int, data: dict) -> dict:
        """Actualiza un producto existente por su ID."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.put(
                f"{self.base_url}/wp-json/wc/v3/products/{product_sku}",
                auth=self.auth,
                json=data
            )
            resp.raise_for_status()
            return resp.json()

    async def create_product(self, data: dict) -> dict:
        """Crea un nuevo producto."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/wp-json/wc/v3/products",
                auth=self.auth,
                json=data
            )
            resp.raise_for_status()
            return resp.json()

    async def get_or_create_category(self, category_name: str, parent: int = None) -> int:
        """Obtiene el ID de una categoría por nombre, o la crea si no existe."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Buscar categorías existentes por nombre (puede devolver varias)
            resp = await client.get(
                f"{self.base_url}/wp-json/wc/v3/products/categories",
                auth=self.auth,
                params={"search": category_name}
            )
            resp.raise_for_status()
            categories = resp.json()
            if categories:
                return categories[0].get("id")
            # Crear nueva categoría, manteniendo jerarquía si parent está dado
            payload = {"name": category_name}
            if parent:
                payload["parent"] = parent
            resp = await client.post(
                f"{self.base_url}/wp-json/wc/v3/products/categories",
                auth=self.auth,
                json=payload
            )
            resp.raise_for_status()
            return resp.json().get("id")
