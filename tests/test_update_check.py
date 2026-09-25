"""The startup update check: version comparison, failure handling, the switch."""
from scanner import update_check as uc


def test_version_parsing_and_comparison():
    assert uc.parse_version("v1.1.3") == (1, 1, 3)
    assert uc.parse_version("1.10.0") > uc.parse_version("v1.9.9")
    assert uc.parse_version("garbage") == (0,)


def test_newer_release_is_reported(capsys, monkeypatch):
    monkeypatch.setattr(uc, "__version__", "1.0.0")
    r = uc.check_once(fetch=lambda: {"tag_name": "v9.0.0", "html_url": "https://example.test/r", "name": "Edge Scanner v9"})
    assert r.available and r.latest == "v9.0.0" and r.url == "https://example.test/r"
    assert "newer release" in capsys.readouterr().out
    assert uc.info().as_dict()["available"] is True


def test_same_or_older_release_is_quiet(capsys):
    r = uc.check_once(fetch=lambda: {"tag_name": "v0.0.1"})
    assert r.checked and not r.available
    assert capsys.readouterr().out == ""


def test_network_failure_is_silent():
    def boom():
        raise OSError("no network")
    r = uc.check_once(fetch=boom)
    assert r.checked and not r.available and r.error


def test_switch_off(monkeypatch):
    monkeypatch.setenv("UPDATE_CHECK", "0")
    assert not uc.enabled()
    monkeypatch.setenv("UPDATE_CHECK", "1")
    assert uc.enabled()
