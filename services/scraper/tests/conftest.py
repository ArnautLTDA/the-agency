"""Pytest fixtures for OSINT Scraper Gateway test suite."""

import pytest
import respx


@pytest.fixture
def sample_business_html() -> str:
    """Returns sample HTML of a local business with contacts and socials."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Barbearia Vintage - Cortes Tradicionais</title></head>
    <body>
        <header>
            <h1>Barbearia Vintage</h1>
            <p>O melhor corte clássico de São Paulo.</p>
        </header>
        <main>
            <h2>Barbearia Vintage</h2>
            <p>Atendimento de segunda a sábado das 09:00 às 20:00.</p>
            <p>Agende pelo WhatsApp ou tire dúvidas por e-mail.</p>
        </main>
        <footer>
            <p>Contato: contato@barbeariavintage.com.br</p>
            <p>Financeiro: financeiro@barbeariavintage.com.br</p>
            <p>CNPJ: 12.345.678/0001-99</p>
            <a href="https://instagram.com/barbearia_vintage_oficial">Siga no Instagram</a>
            <a href="https://wa.me/5511999998888">Agendar no WhatsApp</a>
        </footer>
    </body>
    </html>
    """
