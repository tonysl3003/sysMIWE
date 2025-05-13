# WooIntegration

A micro-service to integrate and synchronize products between a local database or SOAP sources and WooCommerce stores.

## Features

- List products for a client from:
-   - Local database (via stored procedure `obtener_datos_productos`)
-   - SOAP web service (via Zeep client)
- Retrieve WooCommerce inventory
- SOAP warehouse items endpoint
- Background synchronization (stock, images) with WooCommerce
- "Personal" synchronization based on changed-products table
- Compare local vs remote inventories
- Identify and create missing products in WooCommerce
- Update price lists from SOAP sources
- Batch operations script with WhatsApp notifications (via Twilio)

## Requirements

- Python 3.11+
- PostgreSQL (or another DB supported by async SQLAlchemy)
- WooCommerce store(s) with REST API enabled
- (Optional) Twilio account for WhatsApp notifications

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/tu_usuario/wooIntegration.git
   cd wooIntegration
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file based on the following example and fill in your credentials:
   ```dotenv
   # Database URL (asyncpg)
   DATABASE_URL=postgresql+asyncpg://user:password@host:port/dbname

   # API clients (WooCommerce stores)
   CLIENTS_API_JSON='[
     {"client":"client1","url":"https://store.example.com","ck":"ck_xxx","cs":"cs_xxx","dbId":1,"provider":"db"}
   ]'

   # SOAP clients (warehouse bodega)
   SOAP_CREDENTIALS_JSON='[
     {"client":"client1","siretUrl":"example.com","ws_pid":12345,"ws_passwd":"pwd","bid":0}
   ]'

   # Twilio WhatsApp (optional)
   TWILIO_ACCOUNT_SID=your_account_sid
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_FROM_WHATSAPP=whatsapp:+14155238886
   TWILIO_TO_WHATSAPP=whatsapp:+1234567890

   # Base URL for batch sync script (defaults to http://localhost:8000)
   API_BASE_URL=http://localhost:8000
   ```

## Usage

### Run the API

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000 --root-path="/api"
```

The API will be available at `http://localhost:8000/api`.

### API Endpoints

- `GET  /api/` — Hello world
- `GET  /api/health` — Health check (`{"status":"ok"}`)
- `GET  /api/items/{client}` — List products for a client (DB or SOAP)
- `GET  /api/inventory/{client}` — List all WooCommerce products for a client
- `GET  /api/soap/{client}/bodega_items` — SOAP warehouse items for a client
- `POST /api/sync/{client}` — Start background synchronization
- `POST /api/syncPersonal/{client}` — Run personal synchronization and return summary
- `POST /api/clearProdsChange` — Truncate the `prodsChanges` table
- `GET  /api/compare/{client}` — Start background comparison of inventories
- `GET  /api/missingwp/{client}` — List SKUs present locally but missing in WooCommerce
- `POST /api/missingwp/{client}/create` — Start background creation of missing WooCommerce products
- `POST /api/updatePriceList` — Update price lists from predefined SOAP configs

Visit `http://localhost:8000/api/docs` for interactive Swagger UI.

### Batch Sync Script

A helper script `sync_all.py` runs:

- SOAP store operations for all SOAP clients
- `syncPersonal` for all API clients
- Clears the `prodsChanges` table
- Sends a WhatsApp summary via Twilio

Run it with:
```bash
python sync_all.py
```

## Contributing

Feel free to submit issues or pull requests. Please follow the project's coding style and add tests for new features.

## License

MIT