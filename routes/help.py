"""Help blueprint — renders docs/user-guide.md as an in-app knowledge base.

Single source of truth stays the markdown file (kept accurate by the same
docs-audit discipline as the rest of the repo); this just renders it with a
per-tab/per-feature sidebar nav built from the file's real headers, so the
nav can never drift out of sync with the content the way a hand-maintained
TOC can. Re-rendered on every request rather than cached — this is low-
traffic admin tooling, and it means a doc edit shows up without a redeploy.
"""
import html
import logging
import re
from pathlib import Path

import markdown
from flask import Blueprint, abort, render_template

logger = logging.getLogger(__name__)

help_bp = Blueprint('help', __name__, url_prefix='/help')

_DOC_PATH = Path(__file__).resolve().parent.parent / 'docs' / 'user-guide.md'

_MD_EXTENSIONS = ['toc', 'tables', 'fenced_code', 'attr_list', 'sane_lists']
_MD_EXTENSION_CONFIGS = {'toc': {'permalink': False, 'anchorlink': False}}


def _strip_manual_toc(text: str) -> str:
    """Drop the hand-maintained '## Table of Contents' section from the
    source before rendering — the page builds its own sidebar nav from the
    real headers, so keeping a second, separately-maintained TOC in the
    body would just be a second thing that can drift out of sync."""
    return re.sub(r'\n## Table of Contents\n.*?(?=\n## )', '\n', text,
                  count=1, flags=re.DOTALL)


def _unescape_names(tokens: list) -> list:
    """The toc extension's token 'name' is pre-escaped HTML (meant for its
    own toc_tokens-to-HTML renderer, which we don't use) -- e.g. 'Velocity &
    ETA' comes through as 'Velocity &amp; ETA'. Decode it back to plain text
    so Jinja's autoescape (which assumes plain text) doesn't double-escape it
    into 'Velocity &amp;amp; ETA' on the page."""
    for tok in tokens:
        tok['name'] = html.unescape(tok['name'])
        _unescape_names(tok['children'])
    return tokens


def _nav_tree(toc_tokens: list) -> list:
    """Unwrap the single document-title H1 so the sidebar starts at the
    per-tab (H2) level; each tab's H3/H4 features are already nested
    correctly by the markdown toc extension."""
    toc_tokens = _unescape_names(toc_tokens)
    if len(toc_tokens) == 1 and toc_tokens[0]['level'] == 1:
        return toc_tokens[0]['children']
    return toc_tokens


def render_guide():
    """Return (content_html, nav_tree) for the rendered user guide, or
    (None, None) if the source file is missing."""
    if not _DOC_PATH.exists():
        return None, None
    text = _strip_manual_toc(_DOC_PATH.read_text())
    md = markdown.Markdown(extensions=_MD_EXTENSIONS,
                           extension_configs=_MD_EXTENSION_CONFIGS)
    html = md.convert(text)
    return html, _nav_tree(md.toc_tokens)


@help_bp.route('/')
@help_bp.route('')
def index():
    content, nav = render_guide()
    if content is None:
        logger.error('help: docs/user-guide.md not found at %s', _DOC_PATH)
        abort(404)
    return render_template('help/index.html', content=content, nav=nav)
