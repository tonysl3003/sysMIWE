import time
import json
import datetime
import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from dbConn import getProds, AsyncSessionLocal
from getDataClient import getCredentials, wsp_request_bodega_all_items, getSoapCredentials, wsc_request_bodega_all_items
from sqlalchemy import text
from wooCalls import WooCommerceAPI
from fastapi.middleware.cors import CORSMiddleware
from schemas import (
    ItemsResponse,
    InventoryResponse,
    SoapResponse,
    MissingWPResponse,
    MessageResponse,
    PriceListResponse,
)

def log_call(request: Request, client: str):
    prefix = request.url.path.lstrip('/')
    parts = prefix.split('/', 1)
    suffix = parts[1] if len(parts) > 1 else parts[0]
    file_name = f"{suffix.replace('/', '_')}.log"
    with open(file_name, 'a') as f:
        f.write(f"{datetime.datetime.utcnow().isoformat()} - client: {client}\n")

async def fetch_local_products(client: str):
    """Devuelve lista de productos locales y el provider utilizado ('db' o nombre SOAP)."""

    creds = await getCredentials(client)
    if not creds:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    provider = creds.get("provider", "db")
    # Fuente DB
    if provider == "db":
        items = await getProds(creds.get("dbId"))
        return items, provider
    # Fuente SOAP
    soap_creds = await getSoapCredentials(provider)
    if not soap_creds:
        raise HTTPException(status_code=404, detail=f"Proveedor SOAP '{provider}' no encontrado")
    bid = soap_creds.get("bid", 0)
    resp = await wsp_request_bodega_all_items(
        siret_url=soap_creds["siretUrl"],
        ws_pid=soap_creds["ws_pid"],
        ws_passwd=soap_creds["ws_passwd"],
        bid=bid
    )
    raw = resp.get("data", resp)
    items = []
    # Mapear campos SOAP a formato local
    if isinstance(raw, list):
        for it in raw:
            image_url = it.get("image_url")
            image_name = image_url.split("/")[-1] if image_url else None
            items.append({
                "sku": it.get("codigo"),
                "nombre": it.get("descripcion"),
                "precio": it.get("precio"),
                "stock": it.get("stock"),
                "image": image_url,
                "imageName": image_name
            })
    elif isinstance(raw, dict):
        image_url = raw.get("image_url")
        image_name = image_url.split("/")[-1] if image_url else None
        items.append({
            "sku": raw.get("codigo"),
            "nombre": raw.get("descripcion"),
            "precio": raw.get("precio"),
            "stock": raw.get("stock"),
            "image": image_url,
            "imageName": image_name
        })
    return items, provider


app = FastAPI(root_path="/api")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Puedes restringir a ["https://midominio.com"] si quieres más seguro
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/health")
async def healthcheck():
    return {"status": "ok"}
  
@app.exception_handler(OperationalError)
async def sqlalchemy_operational_error_handler(request: Request, exc: OperationalError):
    """
    Catches database OperationalError, maps statement timeouts to 504 and others to 500.
    """
    msg = str(exc.orig) if hasattr(exc, 'orig') else str(exc)
    if 'statement timeout' in msg.lower():
        return JSONResponse(status_code=504, content={'detail': 'Database operation timed out'})
    return JSONResponse(status_code=500, content={'detail': 'Database operational error', 'error': msg})


@app.get(
    "/items/{client}",
    response_model=ItemsResponse,
    tags=["Products"],
)
async def productos(client: str, background_tasks: BackgroundTasks, request: Request):
    """
    Listar productos para un cliente WooCommerce según proveedor configurado.
    Provider 'db' usa la BD, otros usan SOAP definido en la variable de entorno SOAP_CREDENTIALS_JSON.
    """
    log_call(request, client)

    creds = await getCredentials(client)
    if not creds:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    provider = creds.get("provider", "db")

    start = time.time()

    try:
        if provider == "db":
            # Productos desde Base de Datos
            productos_list = await getProds(creds.get("dbId"))
            elapsed = time.time() - start
            payload = {
                "client": client,
                "provider": provider,
                "count": len(productos_list),
                "elapsed": elapsed,
                "productos": productos_list
            }
            return payload

        else:
            # Productos desde SOAP
            soap_creds = await getSoapCredentials(provider)
            if not soap_creds:
                raise HTTPException(status_code=404, detail=f"Proveedor SOAP '{provider}' no encontrado")

            bid = soap_creds.get("bid", 0)
            resp = await wsp_request_bodega_all_items(
                siret_url=soap_creds["siretUrl"],
                ws_pid=soap_creds["ws_pid"],
                ws_passwd=soap_creds["ws_passwd"],
                bid=bid
            )
            raw = resp.get("data", resp)
            allowed = [
                "codigo", "descripcion", "desc_corta", "familia_id", "familia",
                "marca", "clase", "precio", "stock", "image_url",
                "itemref_1", "privacidad"
            ]
            if isinstance(raw, list):
                productos_list = [{k: item.get(k) for k in allowed} for item in raw]
                count = len(productos_list)
            elif isinstance(raw, dict):
                productos_list = {k: raw.get(k) for k in allowed}
                count = 1
            else:
                productos_list = raw
                count = 0

            elapsed = time.time() - start
            payload = {
                "client": client,
                "provider": provider,
                "bid": bid,
                "count": count,
                "elapsed": elapsed,
                "productos": productos_list
            }
            return payload

    except Exception as e:
        elapsed = time.time() - start
        error_message = str(e) or repr(e)
        print(f"Error en productos endpoint para {client}: {error_message}")
        raise HTTPException(status_code=502, detail={"error": error_message, "provider": provider})

@app.get(
    "/inventory/{client}",
    response_model=InventoryResponse,
    tags=["Inventory"],
)
async def list_wp_products(client: str, background_tasks: BackgroundTasks, request: Request):
    """Listar todos los productos del inventario en WooCommerce para un cliente dado."""
    log_call(request, client)
    creds = await getCredentials(client)
    if not creds:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    wc = WooCommerceAPI(creds["url"], creds["ck"], creds["cs"])
    try:
        start = time.time()
        products = await wc.get_all_products()
        elapsed = time.time() - start
        payload = {
            "client": client,
            "dbId": creds.get("dbId"),
            "count": len(products),
            "elapsed": elapsed,
            "productos": products
        }
        # no WhatsApp notification on successful response
        return payload
    except Exception as e:
        elapsed = time.time() - start  # si no la tienes aún
        print(f"Error en inventory endpoint para {client}: {e}")
        raise HTTPException(status_code=502, detail=str(e) or repr(e))

### SOAP multi-cliente: consulta bodega
@app.get(
    "/soap/{client}/bodega_items",
    response_model=SoapResponse,
    tags=["SOAP"],
)
async def soap_bodega_items(client: str, background_tasks: BackgroundTasks, request: Request):
    """
    Consulta todos los ítems de bodega vía SOAP para un cliente configurado en la variable de entorno SOAP_CREDENTIALS_JSON.
    """
    log_call(request, client)
    creds = await getSoapCredentials(client)
    if not creds:
        raise HTTPException(status_code=404, detail="Cliente SOAP no encontrado")

    try:
        # Usar bid definido en configuración SOAP (env SOAP_CREDENTIALS_JSON)
        bid = creds.get("bid", 0)
        start = time.time()
        response = await wsp_request_bodega_all_items(
            siret_url=creds["siretUrl"],
            ws_pid=creds["ws_pid"],
            ws_passwd=creds["ws_passwd"],
            bid=bid
        )
        # Extraer 'data' y filtrar solo campos estándar
        raw = response.get("data", response)
        # Definir campos a exponer en la API
        allowed = [
            "codigo", "descripcion", "desc_corta", "familia_id", "familia",
            "marca", "clase", "precio", "stock", "image_url",
            "itemref_1", "privacidad"
        ]
        # Filtrar registros y contar
        if isinstance(raw, list):
            filtered = [{k: item.get(k) for k in allowed} for item in raw]
            count = len(filtered)
        elif isinstance(raw, dict):
            filtered = {k: raw.get(k) for k in allowed}
            count = 1
        else:
            filtered = raw
            count = 0
        elapsed = time.time() - start
        payload = {
            "client": client,
            "bid": bid,
            "count": count,
            "elapsed": elapsed,
            "data": filtered
        }
        # no WhatsApp notification on successful response
        return payload
    except RuntimeError as e:
        # SOAP request error or timeout
        error_message = str(e)
        print(f"SOAP timeout/error en soap_bodega_items para {client}: {error_message}")
        raise HTTPException(status_code=502, detail=error_message)
    except HTTPException:
        raise
    except Exception as e:
        # Other errors
        error_message = str(e) or repr(e)
        print(f"Error en soap_bodega_items para {client}: {error_message}")
        raise HTTPException(status_code=500, detail=error_message)

@app.post(
    "/sync/{client}",
    response_model=MessageResponse,
    tags=["Sync"],
)
async def sync_remote(client: str, background_tasks: BackgroundTasks, request: Request):
    """Inicia sincronización en segundo plano."""
    log_call(request, client)
    background_tasks.add_task(run_sync_remote, client)
    return {"message": f"Sincronización iniciada para {client}"}

async def run_sync_remote(client: str):
    start = time.time()
    creds = await getCredentials(client)
    if not creds:
        return

    wc = WooCommerceAPI(creds["url"], creds["ck"], creds["cs"])
    changes_log = []  # <-- aquí guardaremos cambios
    changes_count = 0

    try:
        wp_products = await wc.get_all_products()
        local_products, provider = await fetch_local_products(client)

        # Map WooCommerce products by SKU, including image info for sync
        remote_map = {}
        for p in wp_products:
            sku = p.get("sku")
            if not sku:
                continue
            imagen = p.get("imagen") or {}
            remote_map[sku] = {
                "id": p.get("id"),
                "sku": sku,
                "nombre": p.get("nombre") or "",
                "precio": float(p.get("precio") or 0),
                "stock": int(p.get("stock") or 0),
                "image": imagen.get("src"),
                "imageName": imagen.get("name")
            }

        # Map local products by SKU, including image info
        local_map = {}
        for p in local_products:
            sku = p.get("sku")
            if not sku:
                continue
            local_map[sku] = {
                "nombre": p.get("nombre"),
                "precio": p.get("precio"),
                "stock": p.get("stock"),
                "image": p.get("image"),
                "imageName": p.get("imageName")
            }

        shared_skus = set(remote_map) & set(local_map)
        for sku in sorted(shared_skus):
            local = local_map[sku]
            remote = remote_map[sku]
            changes = {}
            # Sync stock if differs
            if int(local.get("stock") or 0) != int(remote.get("stock") or 0):
                changes["stock_quantity"] = int(local.get("stock") or 0)
            # Sync image if name differs
            local_image_name = local.get("imageName")
            remote_image_name = remote.get("imageName")
            if local_image_name != "no image" and local_image_name != remote_image_name:
                local_image_src = local.get("image")
                changes["images"] = [{"src": local_image_src, "name": local_image_name}]

            if changes:
                try:
                    # Use the WooCommerce product ID to perform the update
                    await wc.update_product(remote["id"], changes)
                    changes_count += 1
                    changes_log.append({
                        "sku": sku,
                        "nombre": local.get("nombre"),
                        "cambios": changes
                    })
                except Exception as e:
                    print(f"Error actualizando SKU {sku}: {e}")

        print(f"Sincronización completada para {client}: {changes_count} cambios aplicados.")
        print("Detalle de cambios:")
        for log in changes_log:
            print(log)

    except Exception as e:
        elapsed = time.time() - start
        error_msg = str(e)
        print(f"Error sincronizando {client}: {error_msg}")
@app.post("/syncPersonal/{client}")
async def sync_personal(client: str, request: Request):
    """Ejecuta sincronización personal en primer plano y devuelve el resumen."""
    log_call(request, client)
    # Ejecutar sincronización personal y devolver resultados
    result = await run_sync_personal(client)
    return result

async def run_sync_personal(client: str):
    start = time.time()
    creds = await getCredentials(client)
    if not creds:
        return

    wc = WooCommerceAPI(creds["url"], creds["ck"], creds["cs"])
    changes_log = []
    changes_count = 0

    try:
        # No se consulta el inventario remoto; se procesarán directamente los cambios del procedimiento

        # Fetch changed products from personal table
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("CALL getChangedProds(:userId)"),
                {"userId": creds["dbId"]},
            )
            rows = result.fetchall()

        # Avoid processing duplicate SKUs
        processed_skus = set()
        for row in rows:
            # Extract SKU (case-insensitive)
            sku = getattr(row, 'Sku', None) or getattr(row, 'SKU', None) or getattr(row, 'sku', None)
            if not sku or sku in processed_skus:
                continue
            processed_skus.add(sku)
            # Map new column names: Sku, Name, FamilyxExport, Image, Stock, Sync, Tipo, FinalPrice
            sku = getattr(row, 'Sku', None) or getattr(row, 'SKU', None) or getattr(row, 'sku', None)
            nombre = getattr(row, 'Name', None) or getattr(row, 'NAME', None) or getattr(row, 'nombre', None)
            stock = int(
                getattr(row, 'Stock', None)
                or getattr(row, 'STOCK', None)
                or getattr(row, 'stock', None)
                or 0
            )
            categoria = (
                getattr(row, 'FamilyxExport', None)
                or getattr(row, 'familyxexport', None)
            )
            image_url = (
                getattr(row, 'Image', None)
                or getattr(row, 'image', None)
            )
            # Sync flag: if 2 then hide product
            sync_flag = (
                getattr(row, 'Sync', None)
                or getattr(row, 'sync', None)
                or getattr(row, 'SYNC', None)
            )
            tipo = (
                getattr(row, 'Tipo', None)
                or getattr(row, 'TIPO', None)
                or getattr(row, 'tipo', None)
            )

            if tipo == "Nuevo":
                # Create new product only if price and stock positive
                price = (
                    getattr(row, 'FinalPrice', None)
                    or getattr(row, 'finalprice', None)
                    or getattr(row, 'Finalprice', None)
                    or 0
                )
                if price <= 0 or stock <= 0:
                    continue
                # Determine categories hierarchy
                cats = []
                parent_cat = None
                if categoria:
                    for part in [c.strip() for c in categoria.split('>')]:
                        cid = await wc.get_or_create_category(part, parent_cat)
                        cats.append(cid)
                        parent_cat = cid
                # Prepare creation payload
                data = {
                    "sku": sku,
                    "name": nombre,
                    "type": "simple",
                    "status": "draft" if str(sync_flag) == "2" else "publish",
                    "regular_price": str(price),
                    "stock_quantity": stock
                }
                if cats:
                    data["categories"] = [{"id": cid} for cid in cats]
                # Skip image if 'no image'
                if image_url and image_url.lower() != "no image":
                    data["images"] = [{"src": image_url, "name": image_url.split("/")[-1]}]
                try:
                    await wc.create_product(data)
                    changes_log.append({"sku": sku, "tipo": tipo, "datos": data})
                    changes_count += 1
                except Exception as e:
                    print(f"Error creando SKU {sku}: {e}")

            elif tipo == "Actualizado":
                # Actualizar producto existente por SKU
                changes = {}
                # Fijar stock
                changes["stock_quantity"] = stock
                # Fijar nombre si viene
                if nombre:
                    changes["name"] = nombre
                # Fijar imagen si viene y no es 'no image'
                if image_url and image_url.lower() != "no image":
                    image_name = image_url.split("/")[-1]
                    changes["images"] = [{"src": image_url, "name": image_name}]
                if changes:
                    try:
                        # Intentar obtener ID real del producto por SKU
                        async with httpx.AsyncClient(timeout=wc.timeout) as http_client:
                            resp = await http_client.get(
                                f"{wc.base_url}/wp-json/wc/v3/products",
                                auth=wc.auth,
                                params={"sku": sku}
                            )
                            resp.raise_for_status()
                            found = resp.json() or []
                        # Sync categories if product exists
                        if found and categoria:
                            # Build local category ids hierarchy
                            parts = [c.strip() for c in categoria.split('>')]
                            parent_cat = None
                            local_cats = []
                            for part in parts:
                                cid = await wc.get_or_create_category(part, parent_cat)
                                local_cats.append(cid)
                                parent_cat = cid
                            # Compare with remote categories
                            remote_ids = [c.get("id") for c in found[0].get("categories", [])]
                            if set(local_cats) != set(remote_ids):
                                changes["categories"] = [{"id": cid} for cid in local_cats]
                        # Set hidden status if sync==2
                        if str(sync_flag) == "2":
                            changes["status"] = "draft"
                        if not found:
                            # Si no existe, crear producto desde actualización
                            # Fallback creation for update: same rules as Nuevo
                            price = (
                                getattr(row, 'FinalPrice', None)
                                or getattr(row, 'finalprice', None)
                                or getattr(row, 'Finalprice', None)
                                or 0
                            )
                            if price <= 0 or stock <= 0:
                                continue
                            # Determine categories hierarchy
                            cats = []
                            parent_cat = None
                            if categoria:
                                for part in [c.strip() for c in categoria.split('>')]:
                                    cid = await wc.get_or_create_category(part, parent_cat)
                                    cats.append(cid)
                                    parent_cat = cid
                            data_new = {
                                "sku": sku,
                                "name": nombre,
                                "type": "simple",
                                "status": "draft" if str(sync_flag) == "2" else "publish",
                                "regular_price": str(price),
                                "stock_quantity": stock
                            }
                            if cats:
                                data_new["categories"] = [{"id": cid} for cid in cats]
                            # Skip image if 'no image'
                            if image_url and image_url.lower() != "no image":
                                data_new["images"] = [{"src": image_url, "name": image_url.split("/")[-1]}]
                            try:
                                await wc.create_product(data_new)
                                changes_log.append({"sku": sku, "tipo": tipo, "creado_desde_update": True, "datos": data_new})
                                changes_count += 1
                            except Exception as e:
                                print(f"Error creando SKU {sku} en fallback de update: {e}")
                            continue
                        # Si existe, actualizar usando su ID
                        product_id = found[0].get("id")
                        await wc.update_product(product_id, changes)
                        changes_log.append({"sku": sku, "tipo": tipo, "cambios": changes})
                        changes_count += 1
                    except Exception as e:
                        print(f"Error actualizando SKU {sku}: {e}")
        # Devolver resumen de cambios
        return {"client": client, "changes_count": changes_count, "changes": changes_log}

    except Exception as e:
        elapsed = time.time() - start
        print(f"Error en syncPersonal {client}: {e}")
        # Propagar error para que FastAPI lo maneje
        raise

@app.post(
    "/clearProdsChange",
    response_model=MessageResponse,
    tags=["Sync"],
)
async def clear_prods_change(request: Request):
    """Vacía la tabla prodsChange."""
    log_call(request, "clearProdsChange")
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(text("TRUNCATE TABLE prodsChanges"))
        return {"message": "Tabla prodsChange vaciada"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get(
    "/compare/{client}",
    response_model=MessageResponse,
    tags=["Sync"],
)
async def compare_inventories(client: str, background_tasks: BackgroundTasks, request: Request):
    """Inicia comparación de inventarios en background."""
    log_call(request, client)
    background_tasks.add_task(run_compare_inventories, client)
    return {"message": f"Comparación de inventarios iniciada para {client}"}

async def run_compare_inventories(client: str):
    start = time.time()
    creds = await getCredentials(client)
    if not creds:
        return

    wc = WooCommerceAPI(creds["url"], creds["ck"], creds["cs"])
    try:
        wp_products = await wc.get_all_products()
        local_products, provider = await fetch_local_products(client)

        # Map WooCommerce products by SKU, include ID and image info for comparison or sync
        remote_map = {}
        for p in wp_products:
            sku = p.get("sku")
            if not sku:
                continue
            imagen = p.get("imagen") or {}
            remote_map[sku] = {
                "id": p.get("id"),
                "nombre": p.get("nombre") or "",
                "precio": float(p.get("precio") or 0),
                "stock": int(p.get("stock") or 0),
                "image": imagen.get("src"),
                "imageName": imagen.get("name")
            }

        # Map local products by SKU, include image info for comparison
        local_map = {}
        for p in local_products:
            sku = p.get("sku")
            if not sku:
                continue
            local_map[sku] = {
                "nombre": p.get("nombre"),
                "precio": p.get("precio"),
                "stock": p.get("stock"),
                "image": p.get("image"),
                "imageName": p.get("imageName")
            }

        shared_skus = set(remote_map.keys()) & set(local_map.keys())
        differences = []

        for sku in sorted(shared_skus):
            local = local_map[sku]
            remote = remote_map[sku]
            field_diffs = {}
            # compare stock
            local_stock = int(local.get("stock") or 0)
            remote_stock = int(remote.get("stock") or 0)
            if local_stock != remote_stock:
                field_diffs["stock"] = {"local": local_stock, "remote": remote_stock}
            # compare image names: if mismatch or remote missing, report and insert image
            local_img = local.get("imageName")
            remote_img = remote.get("imageName")
            if local_img != remote_img and local_img != "no image":
                field_diffs["image"] = {"local": local_img, "remote": remote_img}
                if local_img:
                    try:
                        await wc.update_product(remote["id"], {"images": [{"src": local.get("image"), "name": local_img}]})
                        print(f"[{client}] Imagen insertada para SKU {sku}: {local_img}")
                    except Exception as e:
                        print(f"[{client}] Error insertando imagen para SKU {sku}: {e}")
            # record if any differences
            if field_diffs:
                diff = {"sku": sku}
                diff.update(field_diffs)
                differences.append(diff)

        print(f"[{client}] Diferencias encontradas: {len(differences)}")
        if differences:
            print(f"[{client}] Detalles de diferencias:\n{json.dumps(differences, indent=2, ensure_ascii=False, default=str)}")

    except Exception as e:
        elapsed = time.time() - start
        error_msg = str(e)
        print(f"Error comparando inventarios para {client}: {error_msg}")


@app.get(
    "/missingwp/{client}",
    response_model=MissingWPResponse,
    tags=["Products"],
)
async def missingwp(client: str, background_tasks: BackgroundTasks, request: Request):
    """Listar SKUs de productos que están en la BD pero faltan en WooCommerce."""
    log_call(request, client)
    creds = await getCredentials(client)
    if not creds:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    wc = WooCommerceAPI(creds["url"], creds["ck"], creds["cs"])
    try:
        start = time.time()
        # Obtener SKUs existentes en WooCommerce
        products = await wc.get_all_products()
        wp_skus = [p.get("sku") for p in products if p.get("sku")]
        # Obtener SKUs locales según provider
        local_products, provider = await fetch_local_products(client)
        db_skus = [p.get("sku") for p in local_products if p.get("sku")]
        missing_wp = [sku for sku in db_skus if sku not in wp_skus]
        elapsed = time.time() - start
        payload = {
            "client": client,
            "provider": provider,
            "count": len(missing_wp),
            "elapsed": elapsed,
            "missingWp": missing_wp
        }
        # no WhatsApp notification on successful response
        return payload
    except Exception as e:
        elapsed = time.time() - start  # si no la tienes aún
        print(f"Error en missingwp para {client}: {e}")
        raise HTTPException(status_code=502, detail=str(e))

@app.post("/soap/{client}/store")
async def soap_store(client: str, request: Request):
    """Almacena en la base de datos los ítems de bodega obtenidos por SOAP para el cliente dado."""
    log_call(request, client)
    # Obtener credenciales SOAP
    creds = await getSoapCredentials(client)
    if not creds:
        raise HTTPException(status_code=404, detail="Cliente SOAP no encontrado")
    # Identificador de proveedor para insertar en tablas (por defecto 1 si no se provee)
    prov_id = creds.get("provId", 1)
    siret_url = creds.get("siretUrl")
    bid = creds.get("bid", 0)
    try:
        # Llamada SOAP a bodega
        resp = await wsp_request_bodega_all_items(
            siret_url=siret_url,
            ws_pid=creds.get("ws_pid"),
            ws_passwd=creds.get("ws_passwd"),
            bid=bid
        )
        raw = resp.get("data", resp)
        # Asegurar lista de productos
        if isinstance(raw, list):
            products = raw
        elif isinstance(raw, dict):
            products = [raw]
        else:
            products = []
        inserted = 0
        updated = 0
        # Procesar e insertar/actualizar en BD con cargas previas de lookup para eficiencia
        async with AsyncSessionLocal() as session:
            async with session.begin():
                # Preload marcas, subfamilias y productos existentes para reducir roundtrips
                marc_res = await session.execute(
                    text("SELECT descripcion, id FROM marcas WHERE provId = :p"), {"p": prov_id}
                )
                marcas_map = {row[0]: row[1] for row in marc_res.fetchall()}
                sub_res = await session.execute(
                    text("SELECT famId, descripcion FROM subfamilia WHERE provId = :p"), {"p": prov_id}
                )
                subfam_map = {row[0]: row[1] for row in sub_res.fetchall()}
                prod_res = await session.execute(
                    text("SELECT sku, stock, imageUrl FROM productos WHERE provId = :p"), {"p": prov_id}
                )
                productos_map = {row[0]: {"stock": int(row[1] or 0), "imageUrl": row[2] or ""} for row in prod_res.fetchall()}
                for p in products:
                    sku = p.get("codigo")
                    if not sku:
                        continue
                    nombre = p.get("descripcion") or ""
                    fam_id = p.get("familia_id") or 0
                    fam_desc = p.get("familia") or ""
                    marca_desc = p.get("marca") or ""
                    stock = int(p.get("stock") or 0)
                    img = p.get("image_url")
                    image_url = f"https://{siret_url}/{img}" if img else 'no image'
                    # Marca: get or insert
                    marca_id = marcas_map.get(marca_desc)
                    if marca_id is None:
                        await session.execute(
                            text("INSERT INTO marcas (descripcion, provId) VALUES (:d, :p)"),
                            {"d": marca_desc, "p": prov_id}
                        )
                        result = await session.execute(
                            text("SELECT id FROM marcas WHERE descripcion = :d AND provId = :p"),
                            {"d": marca_desc, "p": prov_id}
                        )
                        marca_id = result.scalar_one()
                        marcas_map[marca_desc] = marca_id
                    # Subfamilia: get or insert/update
                    existing_desc = subfam_map.get(fam_id)
                    if existing_desc is not None:
                        if fam_desc and existing_desc != fam_desc:
                            await session.execute(
                                text("UPDATE subfamilia SET descripcion = :d WHERE famId = :f AND provId = :p"),
                                {"d": fam_desc, "f": fam_id, "p": prov_id}
                            )
                            subfam_map[fam_id] = fam_desc
                        subfam_id = fam_id
                    else:
                        await session.execute(
                            text("INSERT INTO subfamilia (famId, descripcion, provId) VALUES (:f, :d, :p)"),
                            {"f": fam_id, "d": fam_desc, "p": prov_id}
                        )
                        subfam_map[fam_id] = fam_desc
                        subfam_id = fam_id
                    # Productos: compare and update/insert
                    existing = productos_map.get(sku)
                    if existing:
                        if existing.get("stock") != stock or existing.get("imageUrl") != image_url:
                            await session.execute(
                                text("UPDATE productos SET stock = :st, imageUrl = :iu WHERE sku = :s"),
                                {"st": stock, "iu": image_url, "s": sku}
                            )
                            await session.execute(
                                text("INSERT INTO prodsChanges (sku, tipo, provId) VALUES (:s, :t, :p)"),
                                {"s": sku, "t": "Actualizado", "p": prov_id}
                            )
                            updated += 1
                    else:
                        await session.execute(
                            text(
                                "INSERT INTO productos (sku, nombre, marcaId, subfamId, stock, imageUrl, provId)"
                                " VALUES (:s, :n, :m, :sf, :st, :iu, :p)"
                            ),
                            {"s": sku, "n": nombre, "m": marca_id, "sf": subfam_id,
                             "st": stock, "iu": image_url, "p": prov_id}
                        )
                        await session.execute(
                            text("INSERT INTO prodsChanges (sku, tipo, provId) VALUES (:s, :t, :p)"),
                            {"s": sku, "t": "Nuevo", "p": prov_id}
                        )
                        inserted += 1
        # Respuesta con resumen de la operación
        return {"client": client, "total": len(products), "inserted": inserted, "updated": updated}
    except RuntimeError as e:
        # External SOAP error or timeout
        raise HTTPException(status_code=502, detail=str(e))
    except HTTPException:
        # propagate HTTPExceptions
        raise
    except Exception as e:
        # Any other error
        raise HTTPException(status_code=500, detail=str(e))

@app.post(
    "/missingwp/{client}/create",
    response_model=MessageResponse,
    tags=["Sync"],
)
async def create_missing_wp(client: str, background_tasks: BackgroundTasks, request: Request):
    """Inicia creación de productos faltantes en WooCommerce en background."""
    log_call(request, client)
    background_tasks.add_task(run_create_missing_wp, client)
    return {"message": f"Creación de productos faltantes iniciada para {client}"}

async def run_create_missing_wp(client: str):
    start = time.time()
    creds = await getCredentials(client)
    if not creds:
        return

    wc = WooCommerceAPI(creds["url"], creds["ck"], creds["cs"])
    try:
        wp_products = await wc.get_all_products()
        wp_skus = {p.get("sku") for p in wp_products if p.get("sku")}
        local_products, provider = await fetch_local_products(client)
        missing_prods = [p for p in local_products if p.get("sku") and p.get("sku") not in wp_skus]

        created = []
        errors = []

        for prod in missing_prods:
            payload = {
                "name": prod.get("nombre"),
                "sku": prod.get("sku"),
                "regular_price": str(prod.get("precio", "0")),
                "stock_quantity": prod.get("stock", 0),
                "manage_stock": True,
                "type": "simple"
            }
            try:
                new_prod = await wc.create_product(payload)
                created.append({"sku": prod.get("sku"), "id": new_prod.get("id")})
            except Exception as e:
                errors.append({"sku": prod.get("sku"), "error": str(e)})

        print(f"[{client}] Productos creados: {len(created)}, Errores: {len(errors)}")
        # no WhatsApp notification on successful response
    except Exception as e:
        elapsed = time.time() - start
        print(f"Error creando productos faltantes para {client}: {e}")


@app.post(
    "/updatePriceList",
    response_model=PriceListResponse,
    tags=["PriceList"],
)
async def updatePriceList():
    """
    Consulta listas desde configuración fija (en el mismo archivo), realiza SOAP, guarda en DB.
    """
    price_lists = [
        {"siretUrl": "ventas.sicsa.com.ni", "ws_cid": 14062, "ws_passwd": "CODE14062", "proveedor": 1, "priceList": "VIP", "bid": 0},
        {"siretUrl": "ventas.sicsa.com.ni", "ws_cid": 14085, "ws_passwd": "CODE14085", "proveedor": 1, "priceList": "PLATINUM", "bid": 0},
        {"siretUrl": "ventas.sicsa.com.ni", "ws_cid": 14057, "ws_passwd": "CODE14057", "proveedor": 1, "priceList": "GOLD", "bid": 0},
        {"siretUrl": "ventas.sicsa.com.ni", "ws_cid": 13244, "ws_passwd": "CODE13244", "proveedor": 1, "priceList": "PUBLICO", "bid": 0},
        {"siretUrl": "ventas.sicsa.com.ni", "ws_cid": 13245, "ws_passwd": "CODE13245", "proveedor": 1, "priceList": "DISTRIBUCION", "bid": 0},
        {"siretUrl": "ventas.sicsa.com.ni", "ws_cid": 12613, "ws_passwd": "CODE12613", "proveedor": 1, "priceList": "OFERTA", "bid": 0},
        # Puedes agregar más aquí
    ]

    results = []

    for cfg in price_lists:
        try:
            print(f"↪️ Procesando lista: {cfg['priceList']}")

            resp = await wsc_request_bodega_all_items(
                siret_url=cfg["siretUrl"],
                ws_cid=cfg["ws_cid"],
                ws_passwd=cfg["ws_passwd"],
                bid=cfg.get("bid", 0)
            )

            print(resp)

            raw = resp.get("data", resp)
            items = raw if isinstance(raw, list) else []

            print(f"[{cfg['priceList']}] Productos recibidos: {len(items)}")

            async with AsyncSessionLocal() as session:
                async with session.begin():
                    # Insert or update price list, ensuring 'descrip' is unique
                    await session.execute(
                        text("""
                            INSERT INTO listaprecio (descrip, prov)
                            VALUES (:descrip, :prov)
                            ON DUPLICATE KEY UPDATE prov = VALUES(prov)
                        """),
                        {"descrip": cfg["priceList"], "prov": cfg["proveedor"]},
                    )
                    # Retrieve the list ID based on unique 'descrip'
                    res = await session.execute(
                        text("SELECT id FROM listaprecio WHERE descrip = :descrip"),
                        {"descrip": cfg["priceList"]},
                    )
                    list_id = res.scalar_one()

                    existing_res = await session.execute(
                        text("SELECT sku, precio FROM preciodetalle WHERE listId = :list_id"),
                        {"list_id": list_id},
                    )
                    existing = {row.sku: row.precio for row in existing_res}

                    # Determine SKUs to upsert (new or price-changed)
                    to_upsert = []
                    inserted = updated = unchanged = 0
                    messages = []

                    for prod in items:
                        sku = prod.get("codigo")
                        price_raw = prod.get("precio")
                        if not sku or price_raw is None:
                            continue
                        try:
                            price = float(price_raw)
                        except:
                            continue

                        old_price = existing.get(sku)
                        if old_price is None:
                            inserted += 1
                            messages.append(f"Insertado SKU: {sku}")
                        elif old_price != price:
                            updated += 1
                            messages.append(f"Actualizado SKU: {sku}")
                        else:
                            unchanged += 1
                            continue

                        to_upsert.append({"sku": sku, "precio": price, "list_id": list_id})

                    # Bulk upsert new and changed prices in one query
                    if to_upsert:
                        await session.execute(
                            text("""
                                INSERT INTO preciodetalle (sku, precio, listId)
                                VALUES (:sku, :precio, :list_id)
                                ON DUPLICATE KEY UPDATE precio = VALUES(precio)
                            """),
                            to_upsert,
                            execution_options={"multi": True},
                        )

            results.append({
                "priceList": cfg["priceList"],
                "listId": list_id,
                "inserted": inserted,
                "updated": updated,
                "unchanged": unchanged,
                "messages": messages[:10]
            })

        except Exception as e:
            # If error, append a result with error message in 'messages'
            results.append({
                "priceList": cfg["priceList"],
                "listId": 0,
                "inserted": 0,
                "updated": 0,
                "unchanged": 0,
                "messages": [f"Error: {str(e)}"]
            })

    return {"results": results}