"""SCANNER_NO_PLUGINS=1 makes the owner's checkout behave like the public build."""
import importlib


def test_no_plugins_env_hides_the_plugin(monkeypatch):
    monkeypatch.setenv("SCANNER_NO_PLUGINS", "1")
    import scanner.plugins as plugins
    plugins = importlib.reload(plugins)
    try:
        assert plugins.SYSTEM_SETUPS == ()
        caps = plugins.capabilities()
        assert caps["system_setups"] is False and caps["tos"] is False
        assert plugins.extra_feeds() == {}
    finally:
        monkeypatch.delenv("SCANNER_NO_PLUGINS")
        importlib.reload(plugins)
