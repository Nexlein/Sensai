from sensai.eval.adversarial.__main__ import main


def test_main_prints_both_levels_and_exits_zero(capsys):
    assert main() == 0
    out = capsys.readouterr().out
    assert "== guardrail level ==" in out
    assert "== engine level ==" in out
    assert "detection rate" in out
