#!/usr/bin/env python3
"""
extract_iics_asset.py - Parse an IICS PROCESS.xml / TASKFLOW.xml export into a
compact JSON "facts" file.

Why this exists: an exported asset XML is mostly boilerplate (GUIDs, option
blocks, namespace noise). An AI agent documenting dozens of these assets
should not have to read tens of thousands of raw-XML tokens per file just to
find the handful of facts (interface, step outline, dependencies, mapping
logic) that actually go in the doc. This script does that extraction
mechanically - zero model calls - and leaves only two things for the model:

  1. A short prose "Overview" (what does this asset do, in business terms).
  2. A 1-2 sentence summary for each XQuery expression longer than 3 lines
     (threshold configurable with --long-threshold).

Everything else (tables, step graph, dependency lists, short mapping rows)
is derived from the XML automatically by render_iics_doc.py.

Usage:
    extract_iics_asset.py <path/to/Asset.PROCESS.xml> -o facts.json
    extract_iics_asset.py <path/to/Asset.TASKFLOW.xml> -o facts.json

The output JSON includes a "needsSummary" list: the exact set of keys the
model must fill in an annotations file before rendering (see
render_iics_doc.py --help).
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

LONG_THRESHOLD_DEFAULT = 3


def strip_ns(tag):
    return tag.split('}', 1)[-1] if '}' in tag else tag


def children(elem, name):
    return [c for c in elem if strip_ns(c.tag) == name]


def child(elem, name):
    for c in elem:
        if strip_ns(c.tag) == name:
            return c
    return None


def text(elem):
    return (elem.text or '').strip() if elem is not None else None


def line_count(expr_text):
    if not expr_text:
        return 0
    non_blank = [l for l in expr_text.splitlines() if l.strip() != '']
    return len(non_blank) if non_blank else (1 if expr_text.strip() else 0)


def parse_field(elem):
    opts = child(elem, 'options')
    ref_to = None
    if opts is not None:
        for opt in children(opts, 'option'):
            if opt.get('name') == 'referenceTo':
                ref_to = text(opt)
    initial_value = None
    if opts is not None:
        for opt in children(opts, 'option'):
            if opt.get('name') == 'initialvalue':
                initial_value = text(opt)
    return {
        'name': elem.get('name'),
        'type': elem.get('type'),
        'description': elem.get('description') or None,
        'referenceTo': ref_to,
        'initialValue': initial_value,
    }


def parse_operation(op, step_id, op_index, long_threshold):
    to = op.get('to')
    source = op.get('source')
    expr_el = child(op, 'expression')
    if expr_el is not None:
        raw = (expr_el.text or '').strip('\n')
        lines = line_count(raw)
        return {
            'key': f'{step_id}#{op_index}',
            'to': to,
            'source': source,
            'language': expr_el.get('language'),
            'value': raw,
            'lineCount': lines,
            'long': lines > long_threshold,
        }
    raw = (op.text or '').strip()
    return {
        'key': f'{step_id}#{op_index}',
        'to': to,
        'source': source,
        'language': None,
        'value': raw,
        'lineCount': 1 if raw else 0,
        'long': False,
    }


def walk_flow(flow_el, steps, links, long_threshold, branch=None):
    for el in flow_el:
        tag = strip_ns(el.tag)
        if tag == 'start':
            for lk in children(el, 'link'):
                links.append({'from': el.get('id'), 'to': lk.get('targetId')})
        elif tag == 'assignment':
            sid = el.get('id')
            title = text(child(el, 'title')) or sid
            ops = [parse_operation(op, sid, i, long_threshold)
                   for i, op in enumerate(children(el, 'operation'))]
            steps.append({'id': sid, 'type': 'assignment', 'title': title,
                           'branch': branch, 'operations': ops})
            for lk in children(el, 'link'):
                links.append({'from': sid, 'to': lk.get('targetId')})
        elif tag == 'service':
            sid = el.get('id')
            title = text(child(el, 'title')) or sid
            service_name = text(child(el, 'serviceName'))
            inputs = []
            svc_in = child(el, 'serviceInput')
            if svc_in is not None:
                for p in children(svc_in, 'parameter'):
                    inputs.append({'name': p.get('name'), 'source': p.get('source'),
                                    'value': (p.text or '').strip()})
            steps.append({'id': sid, 'type': 'service', 'title': title,
                           'branch': branch, 'serviceName': service_name, 'inputs': inputs})
            for lk in children(el, 'link'):
                links.append({'from': sid, 'to': lk.get('targetId')})
        elif tag == 'subflow':
            sid = el.get('id')
            title = text(child(el, 'title')) or sid
            subflow_path = text(child(el, 'subflowPath'))
            steps.append({'id': sid, 'type': 'subflow', 'title': title,
                           'branch': branch, 'subflowPath': subflow_path})
            for lk in children(el, 'link'):
                links.append({'from': sid, 'to': lk.get('targetId')})
        elif tag == 'end':
            sid = el.get('id')
            title = text(child(el, 'title')) or sid
            http_status = text(child(el, 'httpStatus'))
            steps.append({'id': sid, 'type': 'end', 'title': title,
                           'branch': branch, 'httpStatus': http_status})
        elif tag == 'suspend':
            sid = el.get('id')
            title = text(child(el, 'title')) or sid
            steps.append({'id': sid, 'type': 'suspend', 'title': title, 'branch': branch})
        elif tag in ('eventContainer', 'flow'):
            walk_flow(el, steps, links, long_threshold, branch)
        elif tag == 'container':
            ctype = el.get('type')
            ctitle = text(child(el, 'title')) or el.get('id')
            for sub in children(el, 'flow'):
                label = ctitle if ctype == 'exclusive' else f'{ctitle} (parallel)'
                walk_flow(sub, steps, links, long_threshold, label)
        elif tag == 'group':
            for sub in children(el, 'flow'):
                walk_flow(sub, steps, links, long_threshold, branch)
        elif tag == 'catch':
            ctitle = text(child(el, 'title')) or el.get('id') or 'Catch'
            for sub in children(el, 'flow'):
                walk_flow(sub, steps, links, long_threshold, f'{ctitle} (catch)')


def parse_screenflow(root_tag_name, item, long_threshold):
    entry = child(item, 'Entry')
    body = child(entry, root_tag_name) if entry is not None else None
    meta = {
        'name': text(child(item, 'Name')),
        'description': text(child(item, 'Description')),
        'modifiedBy': text(child(item, 'ModifiedBy')),
        'modificationDate': text(child(item, 'ModificationDate')),
        'createdBy': text(child(item, 'CreatedBy')),
        'creationDate': text(child(item, 'CreationDate')),
        'tags': text(child(item, 'Tags')),
    }

    input_fields, output_fields, temp_fields = [], [], []
    core_objects = set()
    if body is not None:
        inp = child(body, 'input')
        if inp is not None:
            for p in children(inp, 'parameter'):
                f = parse_field(p)
                input_fields.append(f)
                if f['referenceTo']:
                    core_objects.add(f['referenceTo'])
        outp = child(body, 'output')
        if outp is not None:
            for p in children(outp, 'field'):
                f = parse_field(p)
                output_fields.append(f)
                if f['referenceTo']:
                    core_objects.add(f['referenceTo'])
        tmp = child(body, 'tempFields')
        if tmp is not None:
            for p in children(tmp, 'field'):
                f = parse_field(p)
                temp_fields.append(f)
                if f['referenceTo']:
                    core_objects.add(f['referenceTo'])

    steps, links = [], []
    if body is not None:
        for fl in children(body, 'flow'):
            walk_flow(fl, steps, links, long_threshold)

    services = sorted({s['serviceName'] for s in steps
                        if s.get('type') == 'service' and s.get('serviceName')})
    subflows = sorted({s['subflowPath'] for s in steps
                        if s.get('type') == 'subflow' and s.get('subflowPath')})

    mappings_short, mappings_long = [], []
    for s in steps:
        if s['type'] != 'assignment':
            continue
        for op in s.get('operations', []):
            row = {
                'key': op['key'], 'stepId': s['id'], 'stepTitle': s['title'],
                'branch': s.get('branch'), 'to': op['to'], 'source': op['source'],
                'value': op['value'], 'lineCount': op['lineCount'],
            }
            (mappings_long if op['long'] else mappings_short).append(row)

    return {
        'meta': meta,
        'input': input_fields, 'output': output_fields, 'tempFields': temp_fields,
        'coreObjects': sorted(core_objects),
        'steps': steps, 'links': links,
        'invokedServices': services, 'invokedSubflows': subflows,
        'mappingsShort': mappings_short, 'mappingsLong': mappings_long,
    }


def extract(xml_path, long_threshold):
    root = ET.parse(xml_path).getroot()
    item = child(root, 'Item')
    if item is None:
        raise ValueError(f'{xml_path}: no <Item> element found (not a recognized IICS export)')
    entry = child(item, 'Entry')
    kind, root_tag = None, None
    if entry is not None and child(entry, 'process') is not None:
        kind, root_tag = 'PROCESS', 'process'
    elif entry is not None and child(entry, 'taskflow') is not None:
        kind, root_tag = 'TASKFLOW', 'taskflow'
    else:
        mime = text(child(item, 'MimeType')) or ''
        kind = 'PROCESS' if 'process' in mime else 'TASKFLOW' if 'taskflow' in mime else 'UNKNOWN'
        root_tag = 'process' if kind == 'PROCESS' else 'taskflow'

    data = parse_screenflow(root_tag, item, long_threshold)
    data['kind'] = kind
    data['sourceFile'] = str(xml_path)

    needs_summary = ['overview'] + [m['key'] for m in data['mappingsLong']]
    data['needsSummary'] = needs_summary
    return data


def build_brief(data):
    """The small, model-facing view: just enough to write prose from.

    This is what you should actually load into context to draft an
    annotations file - not the full facts JSON, which carries every short
    mapping row and raw link graph for the renderer's benefit.
    """
    return {
        'asset': data['meta']['name'],
        'kind': data['kind'],
        'existingDescription': data['meta']['description'],
        'stepTitlesInOrder': [s['title'] for s in data['steps']],
        'invokedServices': data['invokedServices'],
        'invokedSubflows': data['invokedSubflows'],
        'longMappings': [
            {
                'key': m['key'],
                'step': m['stepTitle'],
                'branch': m['branch'],
                'target': m['to'],
                'lineCount': m['lineCount'],
                'xquery': m['value'],
            }
            for m in data['mappingsLong']
        ],
        'instructions': (
            'Write an "overview" string (2-4 sentences, business terms, what '
            'this asset does and when it runs) and one 1-2 sentence "summary" '
            'string per longMappings[].key. Save as annotations JSON: '
            '{"overview": "...", "<key>": "...", ...}. Do not restate the '
            'XQuery in prose; explain intent/business purpose.'
        ),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('xml_path', type=Path, help='Path to *.PROCESS.xml or *.TASKFLOW.xml')
    ap.add_argument('-o', '--out', type=Path, default=None,
                     help='Output JSON path (default: stdout)')
    ap.add_argument('--long-threshold', type=int, default=LONG_THRESHOLD_DEFAULT,
                     help='Line count above which an XQuery expression is pulled into '
                          'Detailed Mapping Logic instead of the summary table (default: 3)')
    ap.add_argument('--brief-out', type=Path, default=None,
                     help='Also write the small model-facing "what needs a summary" '
                          'view (read this, not the full facts file, before drafting '
                          'the annotations JSON)')
    args = ap.parse_args()

    if not args.xml_path.exists():
        print(f'error: {args.xml_path} not found', file=sys.stderr)
        sys.exit(1)

    data = extract(args.xml_path, args.long_threshold)
    out_text = json.dumps(data, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(out_text, encoding='utf-8')
        print(f'Wrote {args.out} ({len(data["steps"])} steps, '
              f'{len(data["mappingsLong"])} long mapping(s) need summaries)', file=sys.stderr)
    else:
        print(out_text)

    if args.brief_out:
        brief = build_brief(data)
        args.brief_out.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Wrote {args.brief_out} (read this one)', file=sys.stderr)


if __name__ == '__main__':
    main()
