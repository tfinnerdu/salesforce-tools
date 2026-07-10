"""CLI tab — page-layout field placement (org-to-org clone-assist).

Salesforce page layouts can't be read synchronously in this stack (the Metadata
API here is async-retrieve-only), so the flow is: retrieve the real layout with
the `sf` CLI, paste it in, and this adds the new fields to it — as a new section
or into an existing one — and hands the modified metadata back to deploy.

Pure string surgery: it inserts `<layoutItems>` (and, for a new section, one
`<layoutSections>` block) and leaves every other byte of the layout untouched.
It is NOT a layout designer — it edits real org metadata, org to org.
"""
import re
from xml.sax.saxutils import escape

# Layout XML uses a fixed 4-space indent: layoutSections=4, layoutColumns=8,
# layoutItems=12, behavior/field=16 (verified across the real Case layouts).
_SECTIONS_CLOSE = '</layoutSections>'


def _field_short(name: str) -> str:
    """Layout <field> uses the bare API name, no object prefix."""
    return name.split('.', 1)[1] if '.' in name else name


def list_sections(layout_xml: str) -> list:
    """Section labels present in a layout, with whether each has an editable
    column (a real <layoutColumns>, not the empty <layoutColumns/> of Custom
    Links). Drives the section picker."""
    sections = []
    for m in re.finditer(r'<layoutSections>(.*?)</layoutSections>', layout_xml, re.DOTALL):
        block = m.group(1)
        label_m = re.search(r'<label>(.*?)</label>', block)
        if not label_m:
            continue
        sections.append({
            'label': label_m.group(1),
            'has_editable_column': '<layoutColumns>' in block,
        })
    return sections


def _existing_fields(layout_xml: str) -> set:
    return set(re.findall(r'<field>(.*?)</field>', layout_xml))


def _item_block(field: str, behavior: str) -> str:
    return (f'            <layoutItems>\n'
            f'                <behavior>{behavior}</behavior>\n'
            f'                <field>{escape(field)}</field>\n'
            f'            </layoutItems>\n')


def _prepare(layout_xml: str, fields: list, behavior: str) -> tuple:
    if _SECTIONS_CLOSE not in layout_xml:
        raise ValueError('This does not look like a Layout metadata file (no <layoutSections>).')
    if behavior not in ('Edit', 'Readonly', 'Required'):
        raise ValueError(f'Unsupported behavior: {behavior!r}')
    present = _existing_fields(layout_xml)
    fresh, skipped = [], []
    for f in fields:
        short = _field_short((f or '').strip())
        if not short:
            continue
        (skipped if short in present else fresh).append(short)
    if not fresh:
        raise ValueError('No fields to add — every field is already on this layout (or the list is empty).')
    return fresh, skipped


def add_new_section(layout_xml: str, section_label: str, fields: list,
                    behavior: str = 'Edit') -> dict:
    """Append a new <layoutSections> (one column of the given fields) right after
    the layout's last section, leaving everything else byte-for-byte unchanged."""
    fresh, skipped = _prepare(layout_xml, fields, behavior)
    items = ''.join(_item_block(f, behavior) for f in fresh)
    section = (
        '    <layoutSections>\n'
        '        <customLabel>true</customLabel>\n'
        '        <detailHeading>true</detailHeading>\n'
        '        <editHeading>true</editHeading>\n'
        f'        <label>{escape(section_label or "New Fields")}</label>\n'
        '        <layoutColumns>\n'
        f'{items}'
        '        </layoutColumns>\n'
        '        <layoutColumns/>\n'
        '        <style>TwoColumnsLeftToRight</style>\n'
        '    </layoutSections>\n'
    )
    idx = layout_xml.rfind(_SECTIONS_CLOSE) + len(_SECTIONS_CLOSE)
    modified = layout_xml[:idx] + '\n' + section.rstrip('\n') + layout_xml[idx:]
    return {'xml': modified, 'added': fresh, 'skipped': skipped}


def add_to_section(layout_xml: str, section_label: str, fields: list,
                   behavior: str = 'Edit') -> dict:
    """Insert the fields as <layoutItems> at the end of the first editable column
    of an existing section, preserving the rest of the file."""
    fresh, skipped = _prepare(layout_xml, fields, behavior)
    label_tag = f'<label>{escape(section_label)}</label>'
    li = layout_xml.find(label_tag)
    if li == -1:
        raise ValueError(f'Section "{section_label}" not found in the layout.')
    section_end = layout_xml.find(_SECTIONS_CLOSE, li)
    col_open = layout_xml.find('<layoutColumns>', li, section_end)  # real (non-empty) column
    if col_open == -1:
        raise ValueError(f'Section "{section_label}" has no editable column to add to — pick another or use a new section.')
    col_close = layout_xml.find('</layoutColumns>', col_open)
    line_start = layout_xml.rfind('\n', 0, col_close) + 1  # start of the </layoutColumns> line
    items = ''.join(_item_block(f, behavior) for f in fresh)
    modified = layout_xml[:line_start] + items + layout_xml[line_start:]
    return {'xml': modified, 'added': fresh, 'skipped': skipped}


def place_fields(layout_xml: str, fields: list, behavior: str = 'Edit',
                 section: str = None, new_section: str = None) -> dict:
    """Dispatch: new_section (create + append) or section (add to existing)."""
    if new_section:
        return add_new_section(layout_xml, new_section, fields, behavior)
    if section:
        return add_to_section(layout_xml, section, fields, behavior)
    raise ValueError('Choose a target: a new section name, or an existing section.')
