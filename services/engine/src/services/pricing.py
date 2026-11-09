"""Dynamic Model Pricing Service for Multi-Provider LLM Telemetry (SEC-016)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    """Pricing rates per million tokens in USD."""

    input_cost_per_m: float
    cached_cost_per_m: float
    output_cost_per_m: float

    def calculate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int,
        usd_brl_rate: float,
    ) -> tuple[float, float]:
        """Calculates precise cost in USD and BRL."""
        non_cached_prompt = max(0, prompt_tokens - cached_tokens)
        cost_prompt = (non_cached_prompt / 1_000_000) * self.input_cost_per_m
        cost_cached = (cached_tokens / 1_000_000) * self.cached_cost_per_m
        cost_completion = (completion_tokens / 1_000_000) * self.output_cost_per_m

        cost_usd = round(cost_prompt + cost_cached + cost_completion, 8)
        cost_brl = round(cost_usd * usd_brl_rate, 8)
        return cost_usd, cost_brl


# Catalog of official pricing rates (SEC-016)
PRICING_CATALOG: dict[str, ModelPricing] = {
    # Gemini Flash family
    "gemini-2.5-flash": ModelPricing(input_cost_per_m=0.075, cached_cost_per_m=0.01875, output_cost_per_m=0.30),
    "gemini-3.5-flash": ModelPricing(input_cost_per_m=0.075, cached_cost_per_m=0.01875, output_cost_per_m=0.30),
    # Gemini Pro family
    "gemini-2.5-pro": ModelPricing(input_cost_per_m=1.25, cached_cost_per_m=0.3125, output_cost_per_m=5.00),
    # Anthropic Claude family
    "claude-3-5-sonnet": ModelPricing(input_cost_per_m=3.00, cached_cost_per_m=0.30, output_cost_per_m=15.00),
    # Groq / Open Source Llama
    "llama-3.3-70b": ModelPricing(input_cost_per_m=0.59, cached_cost_per_m=0.0, output_cost_per_m=0.79),
}

DEFAULT_PRICING = PRICING_CATALOG["gemini-2.5-flash"]


def normalize_model_name(model_name: str) -> str:
    """Normalizes model names by stripping provider prefixes and version tags."""
    clean = model_name.lower().strip()
    if "/" in clean:
        clean = clean.split("/")[-1]
    return clean


def get_model_pricing(model_name: str) -> ModelPricing:
    """Resolves exact ModelPricing from catalog or falls back to default flash baseline."""
    normalized = normalize_model_name(model_name)
    for catalog_key, pricing in PRICING_CATALOG.items():
        if catalog_key in normalized or normalized in catalog_key:
            return pricing
    return DEFAULT_PRICING
