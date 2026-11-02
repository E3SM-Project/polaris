from pathlib import Path

from ruamel.yaml import YAML

#: the campaigns agents read before setting one up
CAMPAIGNS = (
    Path(__file__).resolve().parents[2]
    / 'utils'
    / 'bug_hunt'
    / 'campaigns.yaml'
)


def test_each_campaign_says_what_it_runs_where_and_at_what_cost():
    campaigns = YAML(typ='safe').load(CAMPAIGNS.read_text())

    assert campaigns
    for name, campaign in campaigns.items():
        assert set(campaign) == {'runs', 'rows', 'cost', 'finds', 'setup'}, (
            name
        )
        assert isinstance(campaign['rows'], list), name
        for field in ('runs', 'cost', 'finds', 'setup'):
            assert isinstance(campaign[field], str), (name, field)
