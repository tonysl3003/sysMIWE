import httpx
import json
import asyncio

def cargar_clientes():
    with open("../clientsApi.json", "r") as f:
        return json.load(f)

async def verificar_cliente(cliente):
    url = cliente["url"].rstrip("/") + "/wp-json/wc/v3/products"
    auth = (cliente["ck"], cliente["cs"])

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, auth=auth, params={"per_page": 1})
            r.raise_for_status()
            return {"client": cliente["client"], "estado": "✅ OK", "total": len(r.json())}
    except httpx.ConnectTimeout:
        return {"client": cliente["client"], "estado": "Timeout al conectar"}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {"client": cliente["client"], "estado": " Credenciales inválidas (401)"}
        return {"client": cliente["client"], "estado": f"Error: {str(e)}"}

async def main():
    clientes = cargar_clientes()
    resultados = await asyncio.gather(*(verificar_cliente(c) for c in clientes))

    print("\nResultado de verificación de tiendas WooCommerce:\n")
    for r in resultados:
        print(f"- {r['client']}: {r['estado']}" + (f" ({r['total']} productos)" if "total" in r else ""))

if __name__ == "__main__":
    asyncio.run(main())
