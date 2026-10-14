"""Budget guards do not provision resources or access account credentials."""
import json
from pathlib import Path
import pytest
from scripts.runpod_plan import estimate


def plan():
    return json.loads((Path(__file__).parents[1]/'configs/runpod_trial.json').read_text())


def test_fixed_trial_quote_counts_storage_and_a_reserve():
    cost=estimate(plan(),.89)
    assert cost['gpu_hourly_usd']==.89 and cost['max_hours']==3
    assert cost['storage_upper_estimate_usd']>0
    assert 665<cost['yen_with_reserve']<700


@pytest.mark.parametrize('price',[1.01,float('inf'),float('nan'),-1])
def test_expensive_or_invalid_gpu_quotes_are_rejected(price):
    with pytest.raises(ValueError):estimate(plan(),price)


def test_storage_cost_can_make_an_otherwise_cheap_quote_exceed_budget():
    settings=plan();settings['storage_gb']=20000
    with pytest.raises(ValueError,match='budget'):estimate(settings,.89)
