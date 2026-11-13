"""Lead profile enrichment extracting contact and social details (TC-133)."""

import re
from typing import Any
import httpx
from loguru import logger
from pydantic import BaseModel

from services.extractor import WebpageExtractor


class EnrichedLeadProfile(BaseModel):
    """Enriched contact and social metadata for a lead."""

    lead_id: str
    website: str
    emails: list[str] = []
    instagram_urls: list[str] = []
    whatsapp_links: list[str] = []
    cnpjs: list[str] = []


class LeadEnricher:
    """Enriches leads by crawling their public website."""

    def __init__(self, extractor: WebpageExtractor | None = None) -> None:
        self.extractor = extractor or WebpageExtractor()

    async def enrich(
        self,
        lead_id: str,
        website: str,
        business_name: str = "",
    ) -> EnrichedLeadProfile:
        """Visits website and extracts emails, socials, and contact links (TC-133)."""
        logger.info("Enriching lead {lid} from website {url}", lid=lead_id, url=website)
        emails: set[str] = set()
        instagram_urls: set[str] = set()
        whatsapp_links: set[str] = set()
        cnpjs: set[str] = set()

        try:
            page_res = await self.extractor.fetch_page_markdown(website)
            content = page_res.raw_html or page_res.markdown

            # Extract emails
            found_emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", content)
            for em in found_emails:
                if not em.endswith((".png", ".jpg", ".jpeg", ".svg")):
                    emails.add(em.lower())

            # Extract Instagram
            found_ig = re.findall(r"https?://(?:www\.)?instagram\.com/[a-zA-Z0-9_.]+", content)
            instagram_urls.update(found_ig)

            # Extract WhatsApp
            found_wa = re.findall(r"https?://(?:wa\.me|api\.whatsapp\.com/send)[^\s\"')]+", content)
            whatsapp_links.update(found_wa)

            # Extract CNPJ
            found_cnpj = re.findall(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", content)
            cnpjs.update(found_cnpj)

        except Exception as exc:
            logger.warning("Error fetching website {u} for enrichment: {err}", u=website, err=exc)

        return EnrichedLeadProfile(
            lead_id=lead_id,
            website=website,
            emails=sorted(list(emails)),
            instagram_urls=sorted(list(instagram_urls)),
            whatsapp_links=sorted(list(whatsapp_links)),
            cnpjs=sorted(list(cnpjs)),
        )
