"""Does the model pick the right tool, or none, for a typical request?

Every confirmation is declined, so nothing with side effects runs: the test only
looks at which tools the model asked for.
"""

import pytest

pytestmark = pytest.mark.live

CASES = [
    # Small talk and general knowledge: answer directly.
    ("bonjour", None),
    ("hey", None),
    ("Merci, à plus tard !", None),
    ("Explique-moi une boucle for en Python.", None),
    ("Quelle est la capitale de l'Italie ?", None),
    # Recent or live information: search.
    ("Quelles sont les dernières actualités sur Python cette semaine ?", "web_search"),
    ("Quelle est la météo actuelle à Paris ?", "web_search"),
    ("Qui a gagné le dernier match du PSG ?", "web_search"),
    ("Cherche sur le web la date de l'obligation de tri des biodéchets.", "web_search"),
    # Local files.
    ("Liste les fichiers du dossier courant.", "list_dir"),
    ("Lis le fichier notes.md.", "read_file"),
    ("Écris « brouillon » dans le fichier brouillon.txt.", "write_file"),
    # Code and computation.
    (
        "Exécute un script Python qui affiche la somme des entiers de 1 à 100.",
        "run_python",
    ),
    # Long-term memory.
    ("Retiens que je travaille sur le secteur C.", "remember_fact"),
]


@pytest.mark.parametrize(("prompt", "expected"), CASES)
async def test_model_picks_the_expected_tool(
    workspace, live_session, say, searxng, prompt, expected
):
    (workspace / "notes.md").write_text("Réunion lundi à 9 h.", encoding="utf-8")
    context = await live_session()

    exchange = await say(context, prompt, approve=False)
    print(exchange.transcript())

    called = [c.tool_name for c in exchange.tool_calls]
    if expected is None:
        assert called == [], f"expected a direct answer, got {called}"
        assert exchange.text.strip()
        assert '"name"' not in exchange.text  # no tool call leaked as text
    else:
        assert expected in called, f"expected {expected}, got {called}"
        # Exploring first (list_dir before read_file) is fine; unrelated tools are not.
        assert set(called) <= {expected, "list_dir"}


async def test_forgetting_a_known_fact_asks_for_forget_fact(live_session, say):
    context = await live_session()
    context.structured_memory.store_fact("user", "secteur", "C")

    exchange = await say(
        context, "Oublie mon secteur, il n'est plus d'actualité.", approve=False
    )
    print(exchange.transcript())

    assert "forget_fact" in [c.tool_name for c in exchange.tool_calls]
