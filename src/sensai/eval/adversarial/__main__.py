"""Run the adversarial suite against the default guardrail and print the report.

python -m sensai.eval.adversarial
"""

import asyncio
import sys

from sensai.eval.evaluator import evaluate_engine, evaluate_guardrail
from sensai.eval.guardrails import RegexGuardrail


async def _run() -> int:
    guardrail = RegexGuardrail()
    reports = (
        ("guardrail level", await evaluate_guardrail(guardrail)),
        ("engine level", await evaluate_engine(guardrail)),
    )
    for title, report in reports:
        print(f"== {title} ==")
        print(report.render())
        print()
    return 0 if all(report.ok for _, report in reports) else 1


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
