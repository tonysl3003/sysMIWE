#!/usr/bin/env python3
import os
import json
import sys
try:
    import requests
except ImportError:
    print("Por favor instale 'requests': pip install requests")
    sys.exit(1)
from dotenv import load_dotenv
import asyncio
from utils.whatsapp_notifier import send_whatsapp

def main():
    load_dotenv()
    api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
    # Ejecutar SOAP store para cada cliente
    summary_lines = []
    soap_env = os.getenv("SOAP_CREDENTIALS_JSON", "[]")
    try:
        soap_clients = json.loads(soap_env)
    except json.JSONDecodeError as e:
        print(f"Error parsing SOAP_CREDENTIALS_JSON: {e}")
        soap_clients = []
    for entry in soap_clients:
        client = entry.get("client")
        if not client:
            continue
        url = f"{api_base}/soap/{client}/store"
        try:
            resp = requests.post(url)
            if resp.ok:
                msg = f"[SOAP] {client}: OK -> {resp.text}"
            else:
                msg = f"[SOAP] {client}: ERROR {resp.status_code} -> {resp.text}"
        except Exception as e:
            msg = f"[SOAP] {client}: EXCEPTION -> {e}"
        print(msg)
        summary_lines.append(msg)

    # Ejecutar syncPersonal para cada cliente API
    clients_env = os.getenv("CLIENTS_API_JSON", "[]")
    try:
        api_clients = json.loads(clients_env)
    except json.JSONDecodeError as e:
        print(f"Error parsing CLIENTS_API_JSON: {e}")
        api_clients = []
    for entry in api_clients:
        client = entry.get("client")
        if not client:
            continue
        url = f"{api_base}/syncPersonal/{client}"
        try:
            resp = requests.post(url)
            if resp.ok:
                msg = f"[SYNC] {client}: OK -> {resp.text}"
            else:
                msg = f"[SYNC] {client}: ERROR {resp.status_code} -> {resp.text}"
        except Exception as e:
            msg = f"[SYNC] {client}: EXCEPTION -> {e}"
        print(msg)
        summary_lines.append(msg)

    # Limpiar tabla de cambios
    url = f"{api_base}/clearProdsChange"
    try:
        resp = requests.post(url)
        if resp.ok:
            msg = f"[CLEAR] prodsChange: OK -> {resp.text}"
        else:
            msg = f"[CLEAR] prodsChange: ERROR {resp.status_code} -> {resp.text}"
    except Exception as e:
        msg = f"[CLEAR] prodsChange: EXCEPTION -> {e}"
    print(msg)
    summary_lines.append(msg)

    # Enviar notificación por WhatsApp con el resumen
    try:
        load_dotenv()  # asegurar variables de Twilio cargadas
        resumen = "\n".join(summary_lines)
        asyncio.run(send_whatsapp("sync_all", resumen))
    except Exception as e:
        print(f"Error enviando notificación WhatsApp: {e}")

if __name__ == '__main__':
    main()