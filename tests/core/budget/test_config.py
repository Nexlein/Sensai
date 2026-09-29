import pytest
from pydantic import ValidationError

from sensai.core.budget import BudgetConfig
from sensai.core.config import AppConfig, load_config, save_config


def test_defaults():
    config = BudgetConfig()

    assert config.max_tokens == 8192
    assert config.threshold == 0.8
    assert config.keep_recent_turns == 4


@pytest.mark.parametrize(
    "field, value",
    [
        ("max_tokens", 0),
        ("threshold", 0),
        ("threshold", 1.5),
        ("keep_recent_turns", 0),
    ],
)
def test_out_of_range_values_rejected(field, value):
    with pytest.raises(ValidationError):
        BudgetConfig(**{field: value})


def test_threshold_of_one_is_allowed():
    assert BudgetConfig(threshold=1).threshold == 1


def test_budget_section_loaded_from_file(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config_file.write_text("[budget]\nmax_tokens = 2048\nthreshold = 0.5\n")

    config = load_config(config_file)

    assert config.budget.max_tokens == 2048
    assert config.budget.threshold == 0.5
    assert config.budget.keep_recent_turns == 4


def test_save_config_round_trips_budget(tmp_path):
    config_file = tmp_path / "sensai.toml"
    config = AppConfig(budget=BudgetConfig(max_tokens=2048, keep_recent_turns=2))

    save_config(config, config_file)

    assert load_config(config_file) == config


def test_save_config_omits_default_budget_section(tmp_path):
    config_file = tmp_path / "sensai.toml"

    save_config(AppConfig(), config_file)

    assert "[budget]" not in config_file.read_text()
