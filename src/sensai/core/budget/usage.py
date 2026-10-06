from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetUsage:
    used: int
    max_tokens: int

    @property
    def ratio(self) -> float:
        return self.used / self.max_tokens
