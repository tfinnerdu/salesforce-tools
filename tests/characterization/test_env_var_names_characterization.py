"""
Characterization tests — environment variable name consistency.

Pins that every env var name the app actually reads (config.py) is
documented in .env.example, and that every env var the K8s manifest injects
is one the app actually reads. Per the Doane standard: "Every env var the
service reads -- not values, just that the name is what it is" -- what
should trigger this failing is "Rename in code without updating .env.example
and K8s secrets".

This does NOT assert the reverse (every config.py var must appear in the K8s
manifest) -- most Config fields have safe defaults and legitimately don't
need an explicit k8s override; only secrets and org-specific overrides do.
"""
import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]

# Suffixes get_org_config() builds dynamically via f'{prefix}{suffix}' where
# prefix = f'SF_{org.upper()}_' -- these don't show up as literal
# os.environ.get('SF_...') calls, so they're recognized by suffix instead.
_SF_ORG_SUFFIXES = ('USERNAME', 'PASSWORD', 'TOKEN', 'DOMAIN', 'API_VERSION')


def _is_sf_org_var(name: str) -> bool:
    return name.startswith('SF_') and name.endswith(_SF_ORG_SUFFIXES) and name != 'SF_API_VERSION' \
        and name not in ('SF_BYPASS_FIELD', 'SF_BYPASS_SETTING', 'SF_SOAP_AUTH_VERSION',
                         'SF_DML_RATE_LIMIT')


def _config_env_vars() -> set:
    src = (_ROOT / 'config.py').read_text()
    literal = set(re.findall(r"os\.environ\.get\(\s*['\"]([A-Z_][A-Z0-9_]*)['\"]", src))
    return literal


def _env_example_vars() -> set:
    text = (_ROOT / '.env.example').read_text()
    return set(re.findall(r'^([A-Z_][A-Z0-9_]*)=', text, re.MULTILINE))


def _k8s_env_var_names() -> set:
    docs = list(yaml.safe_load_all((_ROOT / 'k8s' / 'manifest.yaml').read_text()))
    dep = next(d for d in docs if d['kind'] == 'Deployment')
    env = dep['spec']['template']['spec']['containers'][0]['env']
    return {e['name'] for e in env}


def test_every_config_env_var_documented_in_env_example_characterization():
    missing = _config_env_vars() - _env_example_vars()
    assert not missing, (
        f'config.py reads env var(s) {sorted(missing)} that are not documented in '
        '.env.example -- a rename in code without updating .env.example (the exact '
        'drift the standard warns about).'
    )


def test_every_k8s_env_var_is_read_by_the_app_characterization():
    config_vars = _config_env_vars()
    for name in _k8s_env_var_names():
        if _is_sf_org_var(name):
            continue  # built dynamically by get_org_config(), not a literal match
        assert name in config_vars, (
            f'k8s/manifest.yaml injects env var "{name}" but config.py never reads it '
            '(os.environ.get) -- either a typo in the manifest or dead configuration.'
        )


def test_every_k8s_env_var_documented_in_env_example_characterization():
    example_vars = _env_example_vars()
    for name in _k8s_env_var_names():
        assert name in example_vars, (
            f'k8s/manifest.yaml injects env var "{name}" but it is not documented in '
            '.env.example -- local dev has no way to discover it needs setting.'
        )
