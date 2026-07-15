"""Tests for the Help & User Guide page (routes/help.py).

Renders docs/user-guide.md as HTML with a per-tab/per-feature sidebar nav
built from the file's real headers. These tests exercise the render pipeline
against the real doc file (its accuracy is a docs-audit concern, not this
suite's) plus the HTTP wiring and the escaping fix for headers containing
HTML-sensitive characters (e.g. "Velocity & ETA").
"""
import routes.help as help_route
from routes.help import _nav_tree, _strip_manual_toc, _unescape_names, render_guide


class TestStripManualToc:
    def test_removes_toc_section(self):
        text = (
            "# Title\n\n"
            "## Table of Contents\n\n"
            "1. [Foo](#foo)\n"
            "2. [Bar](#bar)\n\n"
            "## Foo\n\ncontent\n"
        )
        out = _strip_manual_toc(text)
        assert 'Table of Contents' not in out
        assert '[Foo](#foo)' not in out
        assert '## Foo' in out
        assert 'content' in out

    def test_noop_when_no_toc_section(self):
        text = "# Title\n\n## Foo\n\ncontent\n"
        assert _strip_manual_toc(text) == text


class TestUnescapeNames:
    def test_decodes_entities_recursively(self):
        tokens = [
            {'level': 2, 'name': 'Velocity &amp; ETA', 'id': 'velocity-eta', 'children': [
                {'level': 3, 'name': 'A &lt; B', 'id': 'a-b', 'children': []},
            ]},
        ]
        out = _unescape_names(tokens)
        assert out[0]['name'] == 'Velocity & ETA'
        assert out[0]['children'][0]['name'] == 'A < B'


class TestNavTree:
    def test_unwraps_single_h1_root(self):
        tokens = [{
            'level': 1, 'name': 'Doc Title', 'id': 'doc-title', 'children': [
                {'level': 2, 'name': 'Tab One', 'id': 'tab-one', 'children': []},
                {'level': 2, 'name': 'Tab Two', 'id': 'tab-two', 'children': []},
            ],
        }]
        nav = _nav_tree(tokens)
        assert [t['name'] for t in nav] == ['Tab One', 'Tab Two']

    def test_leaves_multi_root_tokens_alone(self):
        tokens = [
            {'level': 2, 'name': 'A', 'id': 'a', 'children': []},
            {'level': 2, 'name': 'B', 'id': 'b', 'children': []},
        ]
        assert _nav_tree(tokens) == tokens


class TestRenderGuide:
    def test_renders_real_doc(self):
        content, nav = render_guide()
        assert content is not None
        assert '<h1' in content
        assert nav, 'nav tree should not be empty for the real user guide'

    def test_manual_toc_not_duplicated_in_content(self):
        content, _ = render_guide()
        assert 'id="table-of-contents"' not in content

    def test_headers_get_slug_ids(self):
        content, _ = render_guide()
        assert 'id="getting-started"' in content
        assert 'id="dashboard"' in content

    def test_ampersand_headers_single_escaped_not_double(self):
        # Regression test: the toc extension's token 'name' is pre-escaped
        # ('Velocity &amp; ETA'); Jinja's autoescape must not double-encode
        # it into 'Velocity &amp;amp; ETA' when rendered.
        content, nav = render_guide()
        assert 'Velocity &amp;amp;' not in content

        def find(tokens):
            for t in tokens:
                if 'Velocity' in t['name']:
                    return t['name']
                found = find(t['children'])
                if found:
                    return found
            return None
        name = find(nav)
        assert name == 'Velocity & ETA'

    def test_missing_file_returns_none(self, monkeypatch, tmp_path):
        missing = tmp_path / 'does-not-exist.md'
        monkeypatch.setattr(help_route, '_DOC_PATH', missing)
        content, nav = render_guide()
        assert content is None
        assert nav is None


class TestHelpRoute:
    def test_page_loads(self, client):
        resp = client.get('/help')
        assert resp.status_code == 200
        assert b'Help' in resp.data

    def test_page_contains_sidebar_nav(self, client):
        resp = client.get('/help')
        assert b'id="helpNav"' in resp.data
        assert b'id="helpSearchInput"' in resp.data

    def test_page_includes_known_sections(self, client):
        resp = client.get('/help', follow_redirects=True)
        body = resp.get_data(as_text=True)
        for anchor in ('id="dashboard"', 'id="migration"', 'id="scenarios"',
                      'id="key-maps"', 'id="cli"'):
            assert anchor in body, f'{anchor} missing from rendered guide'

    def test_trailing_slash_variant(self, client):
        resp = client.get('/help/')
        assert resp.status_code == 200

    def test_404_when_doc_missing(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(help_route, '_DOC_PATH', tmp_path / 'gone.md')
        resp = client.get('/help')
        assert resp.status_code == 404


class TestHelpIconInNavbar:
    def test_icon_present_and_positioned_before_logout(self, client):
        resp = client.get('/dashboard')
        body = resp.get_data(as_text=True)
        icon_pos = body.find('mc-help-nav-icon')
        logout_pos = body.find('/logout')
        assert icon_pos != -1, 'help icon missing from navbar'
        assert logout_pos != -1
        assert icon_pos < logout_pos, 'help icon should appear before Logout in the navbar markup'

    def test_icon_links_to_help_page(self, client):
        resp = client.get('/dashboard')
        assert 'href="/help"' in resp.get_data(as_text=True)
