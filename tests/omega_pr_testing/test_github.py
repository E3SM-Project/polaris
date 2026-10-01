import io
import json

import pr_test_github
import pytest


@pytest.fixture
def no_gh(monkeypatch):
    """Queries go to the REST API, as without gh"""
    monkeypatch.setattr(pr_test_github, 'gh_usable', lambda: False)


def test_get_pull_request_without_gh(no_gh, monkeypatch):
    pull = {
        'state': 'closed',
        'merged_at': '2026-10-01T00:00:00Z',
        'draft': False,
        'title': 'Add c',
        'html_url': 'https://github.com/E3SM-Project/Omega/pull/5',
        'head': {'sha': 'a' * 40},
        'base': {'ref': 'develop'},
    }
    monkeypatch.setattr(pr_test_github, 'api_get', lambda path: [pull])

    pr = pr_test_github.get_pull_request(5)

    assert pr == {
        'state': 'MERGED',
        'isDraft': False,
        'title': 'Add c',
        'url': 'https://github.com/E3SM-Project/Omega/pull/5',
        'headRefOid': 'a' * 40,
        'baseRefName': 'develop',
    }


def test_api_get_follows_pages(monkeypatch):
    pages = {
        'https://api.github.com/a': (
            [{'body': 'one'}],
            '<https://api.github.com/b>; rel="next"',
        ),
        'https://api.github.com/b': ([{'body': 'two'}], ''),
    }
    seen = []

    class Response(io.BytesIO):
        def __init__(self, url):
            body, link = pages[url]
            super().__init__(json.dumps(body).encode())
            self.headers = {'Link': link}

    def urlopen(request, timeout):
        seen.append(request)
        return Response(request.full_url)

    monkeypatch.setattr(pr_test_github.urllib.request, 'urlopen', urlopen)
    monkeypatch.delenv('GH_TOKEN', raising=False)
    monkeypatch.setenv('GITHUB_TOKEN', 'secret')

    assert pr_test_github.api_get('a') == [
        [{'body': 'one'}],
        [{'body': 'two'}],
    ]
    assert seen[0].get_header('Authorization') == 'Bearer secret'


def test_get_comment_bodies_without_gh(no_gh, monkeypatch):
    monkeypatch.setattr(
        pr_test_github,
        'api_get',
        lambda path: [[{'body': 'one'}], [{'body': 'two'}]],
    )
    assert pr_test_github.get_comment_bodies(5) == ['one', 'two']


def test_get_requester(no_gh):
    assert pr_test_github.get_requester('git@github.com:me/E3SM.git') == 'me'
    assert (
        pr_test_github.get_requester('https://github.com/you/E3SM.git')
        == 'you'
    )
    with pytest.raises(pr_test_github.GitHubError, match='"fork"'):
        pr_test_github.get_requester(None)


def test_post_comment_needs_gh(no_gh):
    with pytest.raises(pr_test_github.GitHubError, match='by hand'):
        pr_test_github.post_comment(5, '/work/report.md')
