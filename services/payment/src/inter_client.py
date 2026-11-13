"""Banco Inter mTLS HTTP API Client (TC-114, TC-115, TC-120, TC-219)."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import httpx
from loguru import logger
from pydantic import BaseModel

from config import settings


class PixChargeResult(BaseModel):
    """Result of creating a PIX immediate charge."""

    txid: str
    status: str
    pix_copia_e_cola: str
    qr_code_base64: str
    amount_reais: float
    created_at: str


class BancoInterClient:
    """Client for Banco Inter PIX API with mTLS authentication."""

    def __init__(
        self,
        api_base: str = settings.INTER_API_BASE,
        client_id: str = settings.INTER_CLIENT_ID,
        client_secret: str = settings.INTER_CLIENT_SECRET,
        cert_path: str = settings.INTER_CERT_PATH,
        key_path: str = settings.INTER_KEY_PATH,
        pix_key: str = settings.INTER_PIX_KEY,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.cert_path = cert_path
        self.key_path = key_path
        self.pix_key = pix_key
        self._client = client
        self._token: str | None = None
        self._token_expires_at: datetime | None = None

    def _get_cert_tuple(self) -> tuple[str, str] | None:
        """Returns certificate tuple if files exist on disk (TC-179)."""
        from cert_monitor import resolve_cert_path
        cert_p = resolve_cert_path(self.cert_path)
        key_p = resolve_cert_path(self.key_path)
        if cert_p.exists() and key_p.exists():
            return (str(cert_p), str(key_p))
        return None

    def _create_http_client(self) -> httpx.AsyncClient:
        cert = self._get_cert_tuple()
        return httpx.AsyncClient(cert=cert, timeout=15.0)

    async def get_access_token(self) -> str:
        """Obtains OAuth 2.0 Bearer token with mTLS (TC-114)."""
        now = datetime.now(timezone.utc)
        if self._token and self._token_expires_at and now < self._token_expires_at:
            return self._token

        url = f"{self.api_base}/oauth/v2/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": "pix.read pix.write",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        client = self._client or self._create_http_client()
        should_close = self._client is None

        try:
            resp = await client.post(url, data=data, headers=headers)
            resp.raise_for_status()
            res_json = resp.json()
            token = res_json["access_token"]
            expires_in = res_json.get("expires_in", 3600)

            self._token = token
            self._token_expires_at = now + timedelta(seconds=expires_in - 60)
            logger.info("Banco Inter OAuth token obtained successfully")
            return token
        except httpx.HTTPError as exc:
            logger.error("Failed to authenticate with Banco Inter OAuth: {err}", err=exc)
            raise
        finally:
            if should_close:
                await client.aclose()

    async def create_pix_charge(
        self,
        txid: str,
        amount_reais: float,
        debtor_name: str,
        debtor_doc: str,
        description: str,
    ) -> PixChargeResult:
        """Creates an immediate PIX charge via PUT /pix/v2/cob/{txid} (TC-115)."""
        token = await self.get_access_token()
        url = f"{self.api_base}/pix/v2/cob/{txid}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        clean_doc = "".join(filter(str.isdigit, debtor_doc))
        doc_key = "cpf" if len(clean_doc) <= 11 else "cnpj"

        payload = {
            "calendario": {"expiracao": 3600},
            "devedor": {
                "nome": debtor_name,
                doc_key: clean_doc or "00000000000",
            },
            "valor": {"original": f"{amount_reais:.2f}"},
            "chave": self.pix_key,
            "solicitacaoPagador": description[:140],
        }

        client = self._client or self._create_http_client()
        should_close = self._client is None

        try:
            resp = await client.put(url, json=payload, headers=headers)
            resp.raise_for_status()
            cob_data = resp.json()

            pix_copia_e_cola = cob_data.get("pixCopiaECola", "")

            qr_base64 = ""
            try:
                qr_resp = await client.get(f"{url}/qrcode", headers=headers)
                if qr_resp.status_code == 200:
                    qr_data = qr_resp.json()
                    qr_base64 = qr_data.get("imagemQrCode", "")
                    if not pix_copia_e_cola:
                        pix_copia_e_cola = qr_data.get("pixCopiaECola", "")
            except Exception as qr_err:
                logger.debug("QR code fetch error: {err}", err=qr_err)

            return PixChargeResult(
                txid=txid,
                status=cob_data.get("status", "ATIVA"),
                pix_copia_e_cola=pix_copia_e_cola,
                qr_code_base64=qr_base64,
                amount_reais=amount_reais,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        except httpx.HTTPError as exc:
            logger.error("Error creating PIX charge for txid {txid}: {err}", txid=txid, err=exc)
            raise
        finally:
            if should_close:
                await client.aclose()

    async def get_pix_charge_status(self, txid: str) -> dict[str, Any]:
        """Queries status of a PIX charge (TC-120)."""
        token = await self.get_access_token()
        url = f"{self.api_base}/pix/v2/cob/{txid}"
        headers = {"Authorization": f"Bearer {token}"}

        client = self._client or self._create_http_client()
        should_close = self._client is None

        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            logger.error("Error checking PIX status for txid {txid}: {err}", txid=txid, err=exc)
            raise
        finally:
            if should_close:
                await client.aclose()

    async def get_account_balance(self) -> dict[str, Any]:
        """Queries account balance from Banking API."""
        token = await self.get_access_token()
        url = f"{self.api_base}/banking/v2/saldo"
        headers = {"Authorization": f"Bearer {token}"}

        client = self._client or self._create_http_client()
        should_close = self._client is None

        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()
        finally:
            if should_close:
                await client.aclose()

    async def get_billing_metrics(self, start_date: str, end_date: str) -> dict[str, Any]:
        """Consolidates billing metrics and transaction extract."""
        token = await self.get_access_token()
        url = f"{self.api_base}/banking/v2/extrato"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"dataInicio": start_date, "dataFim": end_date}

        client = self._client or self._create_http_client()
        should_close = self._client is None

        try:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            extrato = data.get("transacoes", [])

            total_cents = 0
            count = len(extrato)
            for item in extrato:
                val = float(item.get("valor", 0))
                if val > 0:
                    total_cents += int(round(val * 100))

            ticket_medio = (total_cents / count / 100) if count > 0 else 0.0

            return {
                "period": {"start": start_date, "end": end_date},
                "total_reais": total_cents / 100,
                "transactions_count": count,
                "average_ticket_reais": ticket_medio,
                "extract": extrato,
            }
        finally:
            if should_close:
                await client.aclose()
