from pydantic import BaseModel, Field


class BudgetConfig(BaseModel):
    max_tokens: int = Field(default=8192, gt=0)
    threshold: float = Field(default=0.8, gt=0, le=1)
    keep_recent_turns: int = Field(default=4, ge=1)
