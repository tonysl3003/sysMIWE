import time
import json
import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from dbConn import getProds
from getDataClient import getCredentials, wsp_request_bodega_all_items, getSoapCredentials
from wooCalls import WooCommerceAPI
from fastapi.middleware.cors import CORSMiddleware
from utils.whatsapp_notifier import send_whatsapp_error

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


@app.get("/items/{client}")
async def productos(client: str, background_tasks: BackgroundTasks, request: Request):
    """
    Listar productos para un cliente WooCommerce según proveedor configurado.
    Provider 'db' usa la BD, otros usan SOAP definido en credentialSoap.json.
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
        extra_data = {
            "provider": provider,
            "client": client
        }
        background_tasks.add_task(send_whatsapp_error, client, elapsed, error_message, extra_data)
        raise HTTPException(status_code=502, detail={"error": error_message, "provider": provider})

@app.get("/inventory/{client}")
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
        background_tasks.add_task(send_whatsapp_error, client, elapsed, str(e), {"extra": "informacion util aqui"})

        raise HTTPException(status_code=502, detail=str(e) or repr(e))

### SOAP multi-cliente: consulta bodega
@app.get("/soap/{client}/bodega_items")
async def soap_bodega_items(client: str, background_tasks: BackgroundTasks, request: Request):
    """
    Consulta todos los ítems de bodega vía SOAP para un cliente configurado en credentialSoap.json.
    """
    log_call(request, client)
    creds = await getSoapCredentials(client)
    if not creds:
        raise HTTPException(status_code=404, detail="Cliente SOAP no encontrado")

    try:
        # Usar bid definido en credentialSoap.json
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
    except Exception as e:
        # On error, notify via WhatsApp
        msg = str(e) or repr(e)
        elapsed = time.time() - start
        wsdl_url = f"https://{creds['siretUrl']}:443/webservice.php?wsdl"
        request_info = {
            "wsdl_url": wsdl_url,
            "ws_pid": creds.get("ws_pid"),
            "bid": creds.get("bid", 0)
        }
        background_tasks.add_task(send_whatsapp_error, client, elapsed, msg, request_info)
        raise HTTPException(
            status_code=502,
            detail={"error": msg, "request": request_info}
        )

@app.post("/sync/{client}")
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
        await send_whatsapp_error(client, elapsed, str(e), {"extra": "informacion util aqui"})
        error_msg = str(e)
        print(f"Error sincronizando {client}: {error_msg}")

@app.get("/compare/{client}")
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
        await send_whatsapp_error(client, elapsed, str(e), {"extra": "informacion util aqui"})
        error_msg = str(e)
        print(f"Error comparando inventarios para {client}: {error_msg}")


@app.get("/missingwp/{client}")
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
        background_tasks.add_task(send_whatsapp_error, client, elapsed, str(e), {"extra": "informacion util aqui"})

        raise HTTPException(status_code=502, detail=str(e))

@app.post("/missingwp/{client}/create")
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
        await send_whatsapp_error(client, elapsed, str(e), {"extra": "informacion util aqui"})
        error_msg = str(e)
        print(f"Error creando productos faltantes para {client}: {error_msg}")