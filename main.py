import time
import json
from fastapi import FastAPI, HTTPException, BackgroundTasks
from dbConn import getProds
from getDataClient import getCredentials, wsp_request_bodega_all_items, getSoapCredentials
from wooCalls import WooCommerceAPI


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
            items.append({
                "sku": it.get("codigo"),
                "nombre": it.get("descripcion"),
                "precio": it.get("precio"),
                "stock": it.get("stock")
            })
    elif isinstance(raw, dict):
        items.append({
            "sku": raw.get("codigo"),
            "nombre": raw.get("descripcion"),
            "precio": raw.get("precio"),
            "stock": raw.get("stock")
        })
    return items, provider


app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{client}")
async def productos(client: str):
    """Listar productos para un cliente WooCommerce según proveedor configurado.
    Provider 'db' usa la BD, otros usan SOAP definido en credentialSoap.json."""
    # Obtener configuración del cliente WooCommerce
    creds = await getCredentials(client)
    if not creds:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    # Determinar proveedor (por defecto 'db')
    provider = creds.get("provider", "db")
    # BD local
    if provider == "db":
        start = time.time()
        productos = await getProds(creds.get("dbId"))
        elapsed = time.time() - start
        return {"client": client, "provider": provider,
                "count": len(productos), "elapsed": elapsed,
                "productos": productos}
    # SOAP externo: provider debe corresponder a entry en credentialSoap.json
    soap_creds = await getSoapCredentials(provider)
    if not soap_creds:
        raise HTTPException(status_code=404,
            detail=f"Proveedor SOAP '{provider}' no encontrado")
    # Usar bid definido en la configuración SOAP
    bid = soap_creds.get("bid", 0)
    try:
        start = time.time()
        # Llamada SOAP y filtrado de campos
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
            productos = [{k: item.get(k) for k in allowed} for item in raw]
            count = len(productos)
        elif isinstance(raw, dict):
            productos = {k: raw.get(k) for k in allowed}
            count = 1
        else:
            productos = raw
            count = 0
        elapsed = time.time() - start
        return {"client": client, "provider": provider, "bid": bid,
                "count": count, "elapsed": elapsed,
                "productos": productos}
    except Exception as e:
        msg = str(e) or repr(e)
        wsdl_url = f"https://{soap_creds['siretUrl']}:443/webservice.php?wsdl"
        request_info = {"wsdl_url": wsdl_url,
                        "ws_pid": soap_creds.get("ws_pid"),
                        "bid": bid}
        raise HTTPException(status_code=502,
            detail={"error": msg, "request": request_info})

@app.get("/inventory/{client}")
async def list_wp_products(client: str):
    """Listar todos los productos del inventario en WooCommerce para un cliente dado."""
    creds = await getCredentials(client)
    if not creds:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    wc = WooCommerceAPI(creds["url"], creds["ck"], creds["cs"])
    try:
        start = time.time()
        products = await wc.get_all_products()
        elapsed = time.time() - start
        return {
            "client": client,
            "dbId": creds.get("dbId"),
            "count": len(products),
            "elapsed": elapsed,
            "productos": products
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e) or repr(e))
    
### SOAP multi-cliente: consulta bodega
@app.get("/soap/{client}/bodega_items")
async def soap_bodega_items(client: str):
    """
    Consulta todos los ítems de bodega vía SOAP para un cliente configurado en credentialSoap.json.
    """
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
        return {
            "client": client,
            "bid": bid,
            "count": count,
            "elapsed": elapsed,
            "data": filtered
        }
    except Exception as e:
        msg = str(e) or repr(e)
        wsdl_url = f"https://{creds['siretUrl']}:443/webservice.php?wsdl"
        request_info = {
            "wsdl_url": wsdl_url,
            "ws_pid": creds.get("ws_pid"),
            "bid": creds.get("bid", 0)
        }
        raise HTTPException(
            status_code=502,
            detail={"error": msg, "request": request_info}
        )

@app.post("/sync/{client}")
async def sync_remote(client: str, background_tasks: BackgroundTasks):
    """Inicia sincronización en segundo plano."""
    background_tasks.add_task(run_sync_remote, client)
    return {"message": f"Sincronización iniciada para {client}"}

async def run_sync_remote(client: str):
    creds = await getCredentials(client)
    if not creds:
        return

    wc = WooCommerceAPI(creds["url"], creds["ck"], creds["cs"])
    changes_log = []  # <-- aquí guardaremos cambios
    changes_count = 0

    try:
        wp_products = await wc.get_all_products()
        local_products, provider = await fetch_local_products(client)

        # Map WooCommerce products by SKU, including the product ID for updates
        remote_map = {
            p.get("sku"): {
                "id": p.get("id"),
                "sku": p.get("sku"),
                "nombre": p.get("nombre") or "",
                "precio": float(p.get("precio") or 0),
                "stock": int(p.get("stock") or 0)
            }
            for p in wp_products if p.get("sku")
        }

        local_map = {
            p.get("sku"): {
                "nombre": p.get("nombre"),
                "precio": p.get("precio"),
                "stock": p.get("stock")
            }
            for p in local_products if p.get("sku")
        }

        shared_skus = set(remote_map) & set(local_map)
        for sku in sorted(shared_skus):
            local = local_map[sku]
            remote = remote_map[sku]
            changes = {}
            if int(local.get("stock") or 0) != int(remote.get("stock") or 0):
                changes["stock_quantity"] = int(local.get("stock") or 0)

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
        print(f"Error sincronizando {client}: {e}")

@app.get("/compare/{client}")
async def compare_inventories(client: str, background_tasks: BackgroundTasks):
    """Inicia comparación de inventarios en background."""
    background_tasks.add_task(run_compare_inventories, client)
    return {"message": f"Comparación de inventarios iniciada para {client}"}

async def run_compare_inventories(client: str):
    creds = await getCredentials(client)
    if not creds:
        return

    wc = WooCommerceAPI(creds["url"], creds["ck"], creds["cs"])
    try:
        wp_products = await wc.get_all_products()
        local_products, provider = await fetch_local_products(client)

        remote_map = {
            p.get("sku"): {
                "nombre": p.get("nombre") or "",
                "precio": float(p.get("precio") or 0),
                "stock": int(p.get("stock") or 0)
            }
            for p in wp_products if p.get("sku")
        }

        local_map = {
            p.get("sku"): {
                "nombre": p.get("nombre"),
                "precio": p.get("precio"),
                "stock": p.get("stock")
            }
            for p in local_products if p.get("sku")
        }

        shared_skus = set(remote_map.keys()) & set(local_map.keys())
        differences = []

        for sku in sorted(shared_skus):
            local = local_map[sku]
            remote = remote_map[sku]
            field_diffs = {}
            if int(local.get("stock") or 0) != int(remote.get("stock") or 0):
                field_diffs["stock"] = {"local": local.get("stock"), "remote": remote.get("stock")}
            if field_diffs:
                diff = {"sku": sku}
                diff.update(field_diffs)
                differences.append(diff)

        print(f"[{client}] Diferencias encontradas: {len(differences)}")
        if differences:
            print(f"[{client}] Detalles de diferencias:\n{json.dumps(differences, indent=2, ensure_ascii=False)}")

    except Exception as e:
        print(f"Error comparando inventarios para {client}: {e}")


@app.get("/missingwp/{client}")
async def missingwp(client: str):
    """Listar SKUs de productos que están en la BD pero faltan en WooCommerce."""
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
        return {
            "client": client,
            "provider": provider,
            "count": len(missing_wp),
            "elapsed": elapsed,
            "missingWp": missing_wp
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.post("/missingwp/{client}/create")
async def create_missing_wp(client: str, background_tasks: BackgroundTasks):
    """Inicia creación de productos faltantes en WooCommerce en background."""
    background_tasks.add_task(run_create_missing_wp, client)
    return {"message": f"Creación de productos faltantes iniciada para {client}"}

async def run_create_missing_wp(client: str):
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
    except Exception as e:
        print(f"Error creando productos faltantes para {client}: {e}")