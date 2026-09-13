"""Local-only URL defaults and safe team/repository inputs."""
import pytest

from gauntlet.validate import safe_slug, validate_repo, validate_target


@pytest.mark.parametrize("team,expected", [
    ('../../etc<script>"x', 'etc-script-x'),
    ('  Team  TWO___name  ', 'team-two-name'),
    ('/\\.<>\":', 'team'),
    ('', 'team'),
    ('A' * 100, 'a' * 64),
])
def test_safe_slug(team, expected):
    result = safe_slug(team)
    assert result == expected
    assert len(result) <= 64
    assert not any(character in result for character in '/\\.<>\":')


@pytest.mark.parametrize("repo", [None, 'owner/name', 'owner-name/project_name.git'])
def test_valid_repository(repo):
    assert validate_repo(repo) == repo


@pytest.mark.parametrize("repo", ['bad repo', 'owner', 'owner/name/extra', 'owner/name\n', '', 3])
def test_invalid_repository(repo):
    with pytest.raises(ValueError):
        validate_repo(repo)


@pytest.mark.parametrize("url", [
    'http://localhost:9001', 'https://LOCALHOST./task', 'http://127.0.0.1:9002',
    'http://[::1]:9001', 'http://10.0.0.2', 'http://172.16.0.1',
    'http://172.31.255.254', 'https://192.168.1.1', 'http://target.local:9001',
    'http://[::ffff:127.0.0.1]:9001',
])
def test_local_targets_are_allowed(url):
    assert validate_target(url) == url


@pytest.mark.parametrize("url", ['https://example.com', 'http://8.8.8.8', 'http://172.15.0.1', 'http://172.32.0.1'])
def test_public_targets_require_explicit_remote(url):
    with pytest.raises(ValueError):
        validate_target(url)
    assert validate_target(url, allow_remote=True) == url


@pytest.mark.parametrize("remote", [False, True])
@pytest.mark.parametrize("url", [
    'file:///etc/passwd', 'ftp://localhost', 'http://169.254.169.254/',
    'http://169.254.169.254./', 'http://???????????????/', 'http://[::ffff:169.254.169.254]/',
    'http://2852039166/', 'http://0xa9fea9fe/', 'http://0251.0376.0251.0376/',
    'http://localhost@169.254.169.254/', 'http://localhost:99999',
    'http://localhost:0', 'http://[not-ipv6]', 'http://',
    'http://local\nhost', 'http://localhost\\@example.com',
    'http://localhost:9001?route=task', 'http://localhost:9001/#route',
])
def test_invalid_or_metadata_targets_are_always_refused(url, remote):
    with pytest.raises(ValueError):
        validate_target(url, allow_remote=remote)
