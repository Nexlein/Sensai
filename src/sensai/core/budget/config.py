from pydantic import BaseModel, Field


class BudgetConfig(BaseModel):
    """History compression (M2): when the prompt nears `max_tokens`, old turns are summarized."""

    max_tokens: int = Field(
        default=8192,
        gt=0,
        description="Token budget of a prompt; keep it within options.num_ctx",
    )
    threshold: float = Field(
        default=0.8,
        gt=0,
        le=1,
        description="Share of max_tokens that triggers a summary",
    )
    keep_recent_turns: int = Field(
        default=4, ge=1, description="Latest turns always kept verbatim"
    )
