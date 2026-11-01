"""Computation: is the final answer numerically right, and is `run_python` used well?

Without SENSAI_LIVE_SANDBOX the sandbox is a stub that prints the right result;
the test then still checks that the code the model wrote holds the operands.
"""

import re

import pytest

pytestmark = pytest.mark.live

# Digit-group separators a model may write: space, narrow/no-break space, comma, dot.
_GROUPING = re.compile(r"(?<=\d)[\s  ,.'’](?=\d{3}\b)")


def numbers_in(text: str) -> str:
    """The text with thousand separators removed, so 11 122 453 reads 11122453."""
    previous = None
    while previous != text:
        previous, text = text, _GROUPING.sub("", text)
    return text


def test_numbers_in_removes_thousand_separators():
    assert "11122453" in numbers_in("Le résultat est 11 122 453.")
    assert "11122453" in numbers_in("= 11,122,453")
    assert "11122453" in numbers_in("11 122 453")


@pytest.mark.parametrize(
    ("prompt", "operands", "stdout", "expected"),
    [
        ("Combien font 4817 × 2309 ?", ("4817", "2309"), "11122453", "11122453"),
        (
            "Calcule 987654 * 123456.",
            ("987654", "123456"),
            "121931812224",
            "121931812224",
        ),
        (
            "Combien font 2 puissance 64 ?",
            ("2", "64"),
            "18446744073709551616",
            "18446744073709551616",
        ),
    ],
)
async def test_large_calculation_gets_the_exact_result(
    live_session, say, sandbox, prompt, operands, stdout, expected
):
    context = await live_session()
    tool = sandbox(context, stdout)

    exchange = await say(context, prompt)
    print(exchange.transcript())
    for code in tool.codes:
        print(f"--- run_python code:\n{code}")

    assert expected in numbers_in(exchange.text)
    for code in tool.codes:
        assert all(op in code for op in operands), "code does not use the operands"


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Combien font 12 × 7 ?", "84"),
        ("Combien font 15 % de 200 ?", "30"),
        ("Si un camion fait 3 tournées de 42 km, combien de km au total ?", "126"),
    ],
)
async def test_simple_arithmetic_is_answered_right(
    live_session, say, sandbox, prompt, expected
):
    context = await live_session()
    sandbox(context, expected)

    exchange = await say(context, prompt)
    print(exchange.transcript())

    assert re.search(rf"\b{expected}\b", numbers_in(exchange.text))


async def test_failing_script_is_fixed_and_rerun(live_session, say, monkeypatch):
    """With a sandbox that rejects the first script, the model should retry."""
    from sensai.tools.sandbox import RunCodeTool

    runs: list[str] = []

    class FlakySandbox(RunCodeTool):
        async def execute(self, **kwargs):
            runs.append(kwargs.get("code", ""))
            if len(runs) == 1:
                return (
                    "exit code: 1\nstdout:\n(empty)\nstderr:\n"
                    "NameError: name 'reslt' is not defined"
                )
            return "exit code: 0\nstdout:\n5050\nstderr:\n(empty)"

    context = await live_session()
    context.tool_registry.register(FlakySandbox())

    exchange = await say(
        context, "Exécute un script Python qui affiche la somme des entiers de 1 à 100."
    )
    print(exchange.transcript())

    assert len(runs) >= 2, "the model did not retry after the error"
    assert "5050" in numbers_in(exchange.text)
