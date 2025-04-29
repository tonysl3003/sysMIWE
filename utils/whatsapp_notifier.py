import os
import httpx


async def send_whatsapp(client_name: str, message: str):

    import sys
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_whatsapp = os.getenv("TWILIO_FROM_WHATSAPP")
    to_whatsapp = os.getenv("TWILIO_TO_WHATSAPP")
    missing = [name for name, val in (
        ("TWILIO_ACCOUNT_SID", account_sid),
        ("TWILIO_AUTH_TOKEN", auth_token),
        ("TWILIO_FROM_WHATSAPP", from_whatsapp),
        ("TWILIO_TO_WHATSAPP", to_whatsapp)
    ) if not val]
    if missing:
        print(f"[send_whatsapp] missing env vars: {missing}", file=sys.stderr)
        return
    import json
    # Determinar mensaje resumido para evitar payloads muy grandes
    summary = None
    try:
        payload_json = json.loads(message)
        if isinstance(payload_json, dict) and "count" in payload_json:
            parts = [f"count={payload_json.get('count')}" ]
            # incluir provider o bid si están presentes
            if payload_json.get('provider') is not None:
                parts.append(f"provider={payload_json.get('provider')}")
            if payload_json.get('bid') is not None:
                parts.append(f"bid={payload_json.get('bid')}")
            summary = ", ".join(parts)
    except Exception:
        pass
    if summary is None:
        # Texto libre: quedarnos con la primera línea antes de detalles
        first = message.splitlines()[0]
        # cortar tras marcadores de detalle
        for sep in (" Detalle", " Detalles", ";"):
            if sep in first:
                first = first.split(sep)[0]
                break
        summary = first
    # Construir payload mínimo
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    body = f"Cliente: {client_name}\n{summary}"
    data = {"From": from_whatsapp, "To": to_whatsapp, "Body": body}
    print(f"[send_whatsapp] sending to={to_whatsapp}, url={url}", file=sys.stderr)
    print(f"[send_whatsapp] body: {body}", file=sys.stderr)
    async with httpx.AsyncClient(auth=(account_sid, auth_token), timeout=10) as client:
        try:
            resp = await client.post(url, data=data)
            print(f"[send_whatsapp] status={resp.status_code}, response={resp.text}", file=sys.stderr)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            resp = e.response
            print(f"[send_whatsapp] HTTP error {resp.status_code}: {resp.text}", file=sys.stderr)
        except Exception as e:
            print(f"[send_whatsapp] unexpected error: {e}", file=sys.stderr)