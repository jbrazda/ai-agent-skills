#!/usr/bin/env python3
"""
render_iics_doc.py - Turn facts.json (from extract_iics_asset.py) plus a small
model-authored annotations JSON into the final Markdown asset doc.

This does ALL the mechanical writing: tables, mermaid diagram, the
short/long mapping split, dependency lists, step graph walk. The model's
only job was the prose in annotations.json (overview + long-mapping
summaries); this script never calls a model.

Usage:
    render_iics_doc.py facts.json annotations.json -o doc/Corvel/Asset.md \
        --referenced-docs "doc/Corvel/README.md" "doc/Corvel.md"

annotations.json shape:
    {
      "overview": "...",
      "<mappingKey>": "...",      # one per entry in facts.json mappingsLong
      "errorHandling": "...",      # optional free text appended to Error Handling section
      "logging": "...",            # optional free text appended to Logging section
      "configNotes": "..."         # optional free text appended to Configuration Parameters
    }
"""
import argparse
import json
import re
from pathlib import Path

SECTION_ICONS = {
    'overview': '📘',
    'config': '🔧',
    'interface': '⚙️',
    'diagram': '🏗️',
    'data': '🧬',
    'errors': '⚠️',
    'logging': '📜',
    'deps': '📎',
    'refs': '🔖',
}


def md_table(headers, rows):
    if not rows:
        return None
    out = ['| ' + ' | '.join(headers) + ' |',
           '| ' + ' | '.join(['---'] * len(headers)) + ' |']
    for r in rows:
        out.append('| ' + ' | '.join(str(c).replace('\n', ' ').replace('|', '\\|') for c in r) + ' |')
    return '\n'.join(out)


def esc_mermaid(text_):
    return (text_ or '').replace('"', "'")


def node_id(raw_id):
    return re.sub(r'[^A-Za-z0-9_]', '_', raw_id)


def build_mermaid(steps, links):
    lines = ['flowchart TD']
    shape_fmt = {
        'assignment': ('[', ']'),
        'service': ('([', '])'),
        'subflow': ('[[', ']]'),
        'end': ('(', ')'),
        'suspend': ('{{', '}}'),
    }
    step_ids = {s['id'] for s in steps}
    for s in steps:
        nid = node_id(s['id'])
        left, right = shape_fmt.get(s['type'], ('[', ']'))
        label = esc_mermaid(s['title'])
        if s['type'] == 'service':
            label = f"Call: {label}"
        elif s['type'] == 'subflow':
            label = f"Subprocess: {label}"
        elif s['type'] == 'end':
            status = s.get('httpStatus')
            label = f"{label} ({status})" if status else label
        lines.append(f'    {nid}{left}"{label}"{right}')

    # <start> elements aren't captured as steps; collapse any link originating
    # from one into a single synthetic "Start" node so the diagram has no
    # dangling node IDs.
    start_added = False
    seen = set()
    for lk in links:
        if not lk.get('to') or lk['to'] not in step_ids:
            continue
        from_id = lk['from']
        if from_id not in step_ids:
            if not start_added:
                lines.insert(1, '    START((" Start "))')
                start_added = True
            from_id = 'START'
        else:
            from_id = node_id(from_id)
        key = (from_id, lk['to'])
        if key in seen:
            continue
        seen.add(key)
        lines.append(f'    {from_id} --> {node_id(lk["to"])}')
    return '\n'.join(lines)


def execution_path_summary(steps, annotations):
    lines = []
    for i, s in enumerate(steps, 1):
        branch_note = f' _(branch: {s["branch"]})_' if s.get('branch') else ''
        if s['type'] == 'assignment':
            targets = ', '.join(f'`{op["to"]}`' for op in s.get('operations', []) if op.get('to'))
            desc = f'Sets {targets}.' if targets else 'Performs field assignments.'
        elif s['type'] == 'service':
            desc = f'Calls service `{s.get("serviceName")}`.'
        elif s['type'] == 'subflow':
            desc = f'Invokes subprocess `{s.get("subflowPath")}`.'
        elif s['type'] == 'end':
            status = s.get('httpStatus')
            desc = f'Returns the response{f" (HTTP {status})" if status else ""}.'
        elif s['type'] == 'suspend':
            desc = 'Suspends the process instance.'
        else:
            desc = ''
        lines.append(f'{i}. **{s["title"]}**{branch_note} - {desc}')
    return '\n'.join(lines)


def disambiguate_mappings(mappings_long):
    """Append branch/occurrence suffixes so duplicate step titles are distinct."""
    seen_titles = {}
    for m in mappings_long:
        seen_titles.setdefault(m['stepTitle'], []).append(m)
    labels = {}
    for title, group in seen_titles.items():
        if len(group) == 1:
            labels[group[0]['key']] = title
            continue
        for idx, m in enumerate(group, 1):
            if m.get('branch'):
                labels[m['key']] = f'{title} ({m["branch"]})'
            else:
                labels[m['key']] = f'{title} ({idx} of {len(group)})'
    return labels


def tabs_to_spaces(text_):
    return (text_ or '').expandtabs(4)


def render(facts, ann, referenced_docs, extra_title=None):
    meta = facts['meta']
    title = extra_title or meta.get('name') or 'Asset'
    parts = [f'# {title}', '', '[[_TOC_]]', '']

    # Overview
    parts += [f'## {SECTION_ICONS["overview"]} Overview', '']
    overview = ann.get('overview') or meta.get('description') or '_TODO: add overview._'
    parts += [overview, '']
    meta_rows = []
    if meta.get('modifiedBy') or meta.get('modificationDate'):
        meta_rows.append(('Last modified', f'{meta.get("modificationDate", "n/a")} by `{meta.get("modifiedBy", "n/a")}`'))
    if meta.get('tags'):
        meta_rows.append(('Tags', meta['tags']))
    if meta_rows:
        for k, v in meta_rows:
            parts.append(f'- **{k}:** {v}')
        parts.append('')

    # Configuration Parameters
    parts += [f'## {SECTION_ICONS["config"]} Configuration Parameters', '']
    config_fields = [f for f in facts.get('tempFields', [])
                      if f['name'] and ('config' in f['name'].lower() or f.get('initialValue'))]
    if config_fields:
        rows = [(f'`{f["name"]}`', f.get('initialValue') or '_(set at runtime)_', f.get('description') or '')
                for f in config_fields]
        parts.append(md_table(['Field', 'Default / Source Value', 'Description'], rows))
        parts.append('')
    else:
        parts += ['_No externally configured parameters identified for this asset._', '']
    if ann.get('configNotes'):
        parts += [ann['configNotes'], '']

    # Process Interface
    parts += [f'## {SECTION_ICONS["interface"]} Process Interface', '']
    parts += ['### Input Fields', '']
    if facts['input']:
        rows = [(f'`{f["name"]}`', f['type'] or '', f.get('referenceTo') or '', f.get('description') or '')
                for f in facts['input']]
        parts.append(md_table(['Field', 'Type', 'Reference', 'Description'], rows))
        parts.append('')
    else:
        parts += ['_No input fields._', '']
    parts += ['### Output Fields', '']
    if facts['output']:
        rows = [(f'`{f["name"]}`', f['type'] or '', f.get('referenceTo') or '', f.get('description') or '')
                for f in facts['output']]
        parts.append(md_table(['Field', 'Type', 'Reference', 'Description'], rows))
        parts.append('')
    else:
        parts += ['_No output fields._', '']

    # Process Diagram
    parts += [f'## {SECTION_ICONS["diagram"]} Process Diagram', '']
    parts += [':::mermaid', build_mermaid(facts['steps'], facts['links']), ':::', '']
    parts += ['**Execution path summary:**', '']
    parts += [execution_path_summary(facts['steps'], ann), '']

    # Data Models & Mapping
    parts += [f'## {SECTION_ICONS["data"]} Data Models & Mapping', '']
    parts += ['### Core process objects', '']
    if facts['coreObjects']:
        parts += [f'- `{o}`' for o in facts['coreObjects']]
        parts.append('')
    else:
        parts += ['_None referenced._', '']

    parts += ['### Mapping highlights', '']
    short_rows = [(f'`{m["to"].strip()}`', f'`{m["source"].strip()}`',
                   f'`{m["value"].strip()}`' if m['value'].strip() else '_(empty)_')
                  for m in facts['mappingsShort']]
    table = md_table(['Target', 'Source', 'Expression or Value'], short_rows)
    parts += [table or '_No short-form mappings; see Detailed Mapping Logic below._', '']

    if facts['mappingsLong']:
        parts += ['### Detailed Mapping Logic', '']
        labels = disambiguate_mappings(facts['mappingsLong'])
        for m in facts['mappingsLong']:
            label = labels[m['key']]
            summary = ann.get(m['key']) or '_TODO: add summary for this mapping._'
            parts += [f'#### {label} - `{m["to"]}`', '']
            parts += [summary, '']
            parts += ['```xml', tabs_to_spaces(m['value']), '```', '']

    # Error Handling & Troubleshooting
    parts += [f'## {SECTION_ICONS["errors"]} Error Handling & Troubleshooting', '']
    fault_ends = [s for s in facts['steps'] if s['type'] == 'end' and s.get('httpStatus')
                  and not str(s['httpStatus']).startswith('2')]
    fault_branches = sorted({s['branch'] for s in facts['steps']
                              if s.get('branch') and re.search(r'fault|error|catch|exception', s['branch'], re.I)})
    if fault_ends:
        rows = [(f'`{s["title"]}`', s.get('httpStatus'), s.get('branch') or '-') for s in fault_ends]
        parts.append(md_table(['End Step', 'HTTP Status', 'Branch'], rows))
        parts.append('')
    if fault_branches:
        parts += ['Fault/error branches identified in the flow:', '']
        parts += [f'- {b}' for b in fault_branches]
        parts.append('')
    if not fault_ends and not fault_branches:
        parts += ['_No explicit fault branches identified; errors propagate to the caller via the '
                   'standard process fault contract._', '']
    if ann.get('errorHandling'):
        parts += [ann['errorHandling'], '']

    # Logging
    parts += [f'## {SECTION_ICONS["logging"]} Logging', '']
    log_steps = [s for s in facts['steps'] if re.search(r'^log\b', s['title'], re.I)]
    if log_steps:
        rows = [(f'`{s["title"]}`', s.get('serviceName') or s.get('subflowPath') or '_(inline assignment)_')
                for s in log_steps]
        parts.append(md_table(['Step', 'Target'], rows))
        parts.append('')
    else:
        parts += ['_No dedicated logging steps identified in this asset._', '']
    if ann.get('logging'):
        parts += [ann['logging'], '']

    # Dependencies
    parts += [f'## {SECTION_ICONS["deps"]} Dependencies', '']
    parts += ['### Invoked services', '']
    parts += ([f'- `{s}`' for s in facts['invokedServices']] if facts['invokedServices']
               else ['_None._'])
    parts.append('')
    parts += ['### Invoked subprocesses/taskflows', '']
    parts += ([f'- `{s}`' for s in facts['invokedSubflows']] if facts['invokedSubflows']
               else ['_None._'])
    parts.append('')
    parts += ['### Referenced process objects', '']
    parts += ([f'- `{o}`' for o in facts['coreObjects']] if facts['coreObjects']
               else ['_None._'])
    parts.append('')

    # Referenced Documents
    parts += [f'## {SECTION_ICONS["refs"]} Referenced Documents', '']
    if referenced_docs:
        parts += [f'- [{Path(d).name}]({d})' for d in referenced_docs]
    else:
        parts += [f'- Source asset: `{facts["sourceFile"]}`']
    parts.append('')

    return '\n'.join(parts).rstrip() + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('facts', type=Path, help='facts.json from extract_iics_asset.py')
    ap.add_argument('annotations', type=Path,
                     help='JSON with "overview" + one entry per facts.mappingsLong[].key')
    ap.add_argument('-o', '--out', type=Path, required=True, help='Output .md path')
    ap.add_argument('--title', default=None, help='Override the H1 title (default: asset name)')
    ap.add_argument('--referenced-docs', nargs='*', default=[],
                     help='Paths/links to list under Referenced Documents')
    args = ap.parse_args()

    facts = json.loads(args.facts.read_text(encoding='utf-8'))
    ann = json.loads(args.annotations.read_text(encoding='utf-8')) if args.annotations.exists() else {}

    missing = [k for k in facts.get('needsSummary', []) if k not in ann]
    if missing:
        print('warning: annotations missing keys (rendered with TODO placeholders): '
              + ', '.join(missing))

    doc = render(facts, ann, args.referenced_docs, args.title)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding='utf-8')
    print(f'Wrote {args.out}')


if __name__ == '__main__':
    main()
