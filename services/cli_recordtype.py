"""CLI tab — record-type picklist availability (org-to-org clone-assist).

When a picklist field lives on a record-type-enabled object, its values aren't
available on a record type until that record type's metadata lists them. Same
flow as layouts: retrieve the record type with the CLI, paste it, this adds a
`<picklistValues>` block for the field (or appends values to its existing
block), and hands the modified metadata back to deploy.

Pure string surgery — only the picklist block changes; every other byte is
preserved.

VALUE ENCODING CAVEAT: Salesforce percent-encodes some characters in record-type
picklist value <fullName> (e.g. `/`). Values are written verbatim here — for
values with special characters, paste the encoded form from a retrieved record
type, and always dry-run. Plain code values (MAJ, Email, High) need no encoding.
"""
import re
from xml.sax.saxutils import escape

_PLV_CLOSE = '</picklistValues>'


def list_picklists(rt_xml: str) -> list:
    """Picklist fields already governed in this record type."""
    return re.findall(r'<picklist>(.*?)</picklist>', rt_xml)


def _value_item(value: str, is_default: bool) -> str:
    return (f'        <values>\n'
            f'            <fullName>{escape(value)}</fullName>\n'
            f'            <default>{"true" if is_default else "false"}</default>\n'
            f'        </values>\n')


def _new_block(field: str, values: list, default: str) -> str:
    items = ''.join(_value_item(v, v == default) for v in values)
    return (f'    <picklistValues>\n'
            f'        <picklist>{escape(field)}</picklist>\n'
            f'{items}'
            f'    </picklistValues>')


def add_picklist_values(rt_xml: str, field: str, values: list, default: str = None) -> dict:
    """Make `values` available for picklist `field` on this record type.

    If the record type already governs `field`, missing values are appended to
    that block; otherwise a new `<picklistValues>` block is added. `default`
    (optional) marks one value as the record type's default.
    """
    if '<RecordType' not in rt_xml:
        raise ValueError('This does not look like a RecordType metadata file.')
    field = (field or '').strip()
    if not field:
        raise ValueError('A picklist field API name is required.')
    values = [v.strip() for v in (values or []) if v and v.strip()]
    if not values:
        raise ValueError('Add at least one picklist value.')

    block_re = re.compile(
        r'<picklistValues>\s*<picklist>' + re.escape(field) + r'\s*</picklist>.*?</picklistValues>',
        re.DOTALL)
    m = block_re.search(rt_xml)

    if m:
        block = m.group(0)
        existing = set(re.findall(r'<fullName>(.*?)</fullName>', block))
        fresh = [v for v in values if v not in existing]
        if not fresh:
            raise ValueError(f'All values are already available for {field} on this record type.')
        items = ''.join(_value_item(v, v == default) for v in fresh)
        close_at = m.start() + block.rfind(_PLV_CLOSE)      # the block's </picklistValues>
        line_start = rt_xml.rfind('\n', 0, close_at) + 1     # start of that line
        modified = rt_xml[:line_start] + items + rt_xml[line_start:]
        return {'xml': modified, 'field': field, 'added': fresh,
                'skipped': sorted(existing & set(values)), 'mode': 'appended'}

    block = _new_block(field, values, default)
    anchor = rt_xml.rfind(_PLV_CLOSE)
    if anchor != -1:
        pos = anchor + len(_PLV_CLOSE)
    else:
        lbl = rt_xml.find('</label>')
        if lbl == -1:
            raise ValueError('Could not find an insertion point (no <label> or <picklistValues>).')
        pos = lbl + len('</label>')
    modified = rt_xml[:pos] + '\n' + block + rt_xml[pos:]
    return {'xml': modified, 'field': field, 'added': values, 'skipped': [], 'mode': 'new-block'}
