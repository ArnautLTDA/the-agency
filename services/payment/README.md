# Payment Gateway & Banco Inter Integration (Port :3006)

Financial gateway managing:
- Banco Inter mTLS API client (OAuth 2.0 Client Credentials, PIX Cob immediate charges, QR Code)
- PIX webhook receiver (`/api/v1/inter/webhook`) with `x-webhook-key` validation and IP whitelist
- Central SQLite updates (`pix_transactions`, `leads` stage advancement to `DEV`)
- RabbitMQ event publication (`payment.webhooks`)
- Native MCP Server exposing `create_pix_charge` and `check_pix_status`
