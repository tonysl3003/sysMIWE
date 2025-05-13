import json
import asyncio
import requests
from zeep import Client as ZeepClient
from zeep.transports import Transport
from zeep.helpers import serialize_object


# Cargar credenciales desde la variable de entorno CLIENTS_API_JSON
import os
_creds_env = os.getenv("CLIENTS_API_JSON", "[]")
try:
    _credentials = json.loads(_creds_env)
except json.JSONDecodeError:
    _credentials = []

async def getCredentials(cliente: str):
    """Obtener credenciales de un cliente desde la variable de entorno CLIENTS_API_JSON."""
    for entry in _credentials:
        if entry.get("client") == cliente:
            return entry
    return None


# Cargar configuración de clientes SOAP desde la variable de entorno SOAP_CREDENTIALS_JSON
_soap_env = os.getenv("SOAP_CREDENTIALS_JSON", "[]")
try:
    _soap_credentials = json.loads(_soap_env)
except json.JSONDecodeError:
    _soap_credentials = []

async def getSoapCredentials(cliente: str):

    """Obtener credenciales de un cliente SOAP desde la variable de entorno SOAP_CREDENTIALS_JSON."""

    for entry in _soap_credentials:
        if entry.get("client") == cliente:
            return entry
    return None

def _sync_request_bodega_all_items(
    siret_url: str,
    ws_pid: int,
    ws_passwd: str,
    bid: int
) -> dict:

    """Consulta SOAP al servicio wsp_request_bodega_all_items.
    Devuelve el objeto serializado en diccionario."""

    # Construir URL del WSDL
    wsdl_url = f"https://{siret_url}:443/webservice.php?wsdl"
    # Crear sesión requests sin influir de proxies de entorno
    session = requests.Session()
    session.trust_env = False
    # Cliente sincrónico Zeep con timeout (10s) para evitar colgado indefinido
    transport = Transport(session=session, timeout=10)
    client = ZeepClient(wsdl=wsdl_url, transport=transport)
    try:
        # Invocar operación con parámetros nombrados
        response = client.service.wsp_request_bodega_all_items(
            ws_pid=ws_pid,
            ws_passwd=ws_passwd,
            bid=bid
        )
        # Serializar objeto Zeep a tipos nativos Python
        return serialize_object(response)
    except Exception as e:
        # Timeout u otro error de conexión SOAP
        raise RuntimeError(f"SOAP request failed: {e}")

def _sync_request_bodega_all_items_client(
    siret_url: str,
    ws_cid: int,
    ws_passwd: str,
    bid: int
) -> dict:

    """Consulta SOAP al servicio wsp_request_bodega_all_items.
    Devuelve el objeto serializado en diccionario."""

    # Construir URL del WSDL
    wsdl_url = f"https://{siret_url}:443/webservice.php?wsdl"
    # Crear sesión requests sin influir de proxies de entorno
    session = requests.Session()
    session.trust_env = False
    # Cliente sincrónico Zeep con timeout (10s) para evitar colgado indefinido
    transport = Transport(session=session, timeout=10)
    client = ZeepClient(wsdl=wsdl_url, transport=transport)
    try:
        # Invocar operación con parámetros nombrados
        response = client.service.wsc_request_bodega_all_items(
            ws_cid=ws_cid,
            ws_passwd=ws_passwd,
            bid=bid
        )
        # Serializar objeto Zeep a tipos nativos Python
        return serialize_object(response)
    except Exception as e:
        # Timeout u otro error de conexión SOAP
        raise RuntimeError(f"SOAP client request failed: {e}")

async def wsp_request_bodega_all_items(
    siret_url: str,
    ws_pid: int,
    ws_passwd: str,
    bid: int
) -> dict:
    """Llamada asíncrona al servicio SOAP (bloquea en ThreadPool) y serializa la respuesta."""

    return await asyncio.to_thread(
        _sync_request_bodega_all_items,
        siret_url,
        ws_pid,
        ws_passwd,
        bid,
    )

async def wsc_request_bodega_all_items(
    siret_url: str,
    ws_cid: int,
    ws_passwd: str,
    bid: int
) -> dict:
    """Llamada asíncrona al servicio SOAP (bloquea en ThreadPool) y serializa la respuesta."""

    return await asyncio.to_thread(
        _sync_request_bodega_all_items_client,
        siret_url,
        ws_cid,
        ws_passwd,
        bid,
    )