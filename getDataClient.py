import json
import asyncio
import requests
from zeep import Client as ZeepClient
from zeep.transports import Transport
from zeep.helpers import serialize_object


# Cargar credenciales una sola vez en memoria
_credentials = json.load(open("clientsApi.json", "r"))

async def getCredentials(cliente: str):
    """Obtener credenciales de un cliente desde memoria."""
    for entry in _credentials:
        if entry.get("client") == cliente:
            return entry
    return None


# Cargar configuración de clientes SOAP
_soap_credentials = json.load(open("credentialSoap.json", "r"))

async def getSoapCredentials(cliente: str):

    """Obtener credenciales de un cliente SOAP desde credentialSoap.json."""

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
    transport = Transport(session=session)
    # Cliente sincrónico Zeep
    client = ZeepClient(wsdl=wsdl_url, transport=transport)
    # Invocar operación con parámetros nombrados
    response = client.service.wsp_request_bodega_all_items(
        ws_pid=ws_pid,
        ws_passwd=ws_passwd,
        bid=bid
    )
    # Serializar objeto Zeep a tipos nativos Python
    return serialize_object(response)

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
    transport = Transport(session=session)
    # Cliente sincrónico Zeep
    client = ZeepClient(wsdl=wsdl_url, transport=transport)
    # Invocar operación con parámetros nombrados
    response = client.service.wsc_request_bodega_all_items(
        ws_cid=ws_cid,
        ws_passwd=ws_passwd,
        bid=bid
    )
    # Serializar objeto Zeep a tipos nativos Python
    return serialize_object(response)

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