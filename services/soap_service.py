import time
from getDataClient import wsp_request_bodega_all_items, wsc_request_bodega_all_items, getSoapCredentials
from schemas import ALLOWED_SOAP_FIELDS

def _filter_fields(raw):
    """Filtra campos de respuesta SOAP según ALLOWED_SOAP_FIELDS."""
    if isinstance(raw, list):
        return [{k: item.get(k) for k in ALLOWED_SOAP_FIELDS} for item in raw]
    if isinstance(raw, dict):
        return {k: raw.get(k) for k in ALLOWED_SOAP_FIELDS}
    return raw

async def fetch_bodega_items(provider: str):
    """Obtiene y filtra ítems de bodega usando wsp_request_bodega_all_items."""
    creds = await getSoapCredentials(provider)
    if not creds:
        raise ValueError(f"Proveedor SOAP '{provider}' no encontrado")
    bid = creds.get("bid", 0)
    start = time.time()
    resp = await wsp_request_bodega_all_items(
        siret_url=creds["siretUrl"],
        ws_pid=creds["ws_pid"],
        ws_passwd=creds["ws_passwd"],
        bid=bid
    )
    raw = resp.get("data", resp)
    items = _filter_fields(raw)
    elapsed = time.time() - start
    return items, provider, bid, elapsed

async def fetch_client_bodega_items(provider: str):
    """Obtiene y filtra ítems de bodega cliente usando wsc_request_bodega_all_items."""
    creds = await getSoapCredentials(provider)
    if not creds:
        raise ValueError(f"Proveedor SOAP '{provider}' no encontrado")
    bid = creds.get("bid", 0)
    start = time.time()
    resp = await wsc_request_bodega_all_items(
        siret_url=creds["siretUrl"],
        ws_cid=creds.get("ws_cid"),
        ws_passwd=creds["ws_passwd"],
        bid=bid
    )
    raw = resp.get("data", resp)
    items = _filter_fields(raw)
    elapsed = time.time() - start
    return items, provider, bid, elapsed