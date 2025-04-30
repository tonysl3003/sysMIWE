async def send_whatsapp_error(client_name: str, elapsed: float, error: str, data: dict = None):
    import sys
    import os
    import httpx
    import json

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_whatsapp = os.getenv("TWILIO_FROM_WHATSAPP")
    to_whatsapp = os.getenv("TWILIO_TO_WHATSAPP")

    if not all([account_sid, auth_token, from_whatsapp, to_whatsapp]):
        print("[send_whatsapp_error] Missing Twilio env vars", file=sys.stderr)
        return

    # Armar mensaje
    message = f"Cliente: {client_name}\n"
    message += f"Tiempo Ejecución: {elapsed:.2f} segundos\n"
    message += f"Error: {error}\n"
    if data:
        try:
            data_str = json.dumps(data, ensure_ascii=False, indent=2)
            message += f"Datos analizados:\n{data_str}"
        except Exception:
            message += "Datos analizados: [Error al formatear JSON]"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = {"From": from_whatsapp, "To": to_whatsapp, "Body": message}

    async with httpx.AsyncClient(auth=(account_sid, auth_token), timeout=10) as client:
        try:
            resp = await client.post(url, data=data)
            print(f"[send_whatsapp_error] status={resp.status_code}, response={resp.text}", file=sys.stderr)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"[send_whatsapp_error] HTTP error {e.response.status_code}: {e.response.text}", file=sys.stderr)
        except Exception as e:
            print(f"[send_whatsapp_error] unexpected error: {e}", file=sys.stderr)
    
async def send_whatsapp(client_name: str, message: str):
    import sys
    import os
    import httpx

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_whatsapp = os.getenv("TWILIO_FROM_WHATSAPP")
    to_whatsapp = os.getenv("TWILIO_TO_WHATSAPP")

    if not all([account_sid, auth_token, from_whatsapp, to_whatsapp]):
        print("[send_whatsapp] Missing Twilio env vars", file=sys.stderr)
        return

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = {"From": from_whatsapp, "To": to_whatsapp, "Body": message}

    async with httpx.AsyncClient(auth=(account_sid, auth_token), timeout=10) as client:
        try:
            resp = await client.post(url, data=data)
            print(f"[send_whatsapp] status={resp.status_code}, response={resp.text}", file=sys.stderr)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"[send_whatsapp] HTTP error {e.response.status_code}: {e.response.text}", file=sys.stderr)
        except Exception as e:
            print(f"[send_whatsapp] unexpected error: {e}", file=sys.stderr)
