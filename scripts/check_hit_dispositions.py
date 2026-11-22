"""Exact disposition gate for all scan categories, including rescanned hits.
Generate pending ledger when missing; never treats count thresholds as completion.
"""
import argparse
import re
from pathlib import Path
from review_state import read, save, hit_records, digest


def verify(hits_path, worklist, ledger_path):
    expected = hit_records(read(hits_path))
    errors = []
    old = read(ledger_path) if Path(ledger_path).exists() else {}
    prior = {x['id']:x for x in old.get('items',[])}
    items = []
    for x in expected:
        previous = prior.get(x['id'])
        if previous and previous.get('text') == x['text'] and old.get('lines_sha256') == digest(read(hits_path)['source']):
            x = previous
        items.append(x)
    data = {'hits_sha256':digest(hits_path),'lines_sha256':digest(read(hits_path)['source']), 'items':items}
    save(ledger_path,data)
    md = Path(worklist).read_text(encoding='utf-8')
    for x in items:
        if x.get('status') not in ('included','excluded','duplicate') or not x.get('reason'):
            errors.append('未处置：' + x['id'])
        elif x['status'] != 'excluded':
            report_id = x.get('report_id','')
            matching = [r for r in md.splitlines() if r.startswith('|') and report_id and report_id in [c.strip() for c in r.split('|')]]
            if not matching or not any(any(int(m[0]) <= x['line'] <= int(m[1] or m[0]) for m in re.findall(r'行\s*(\d+)(?:\s*[-–至]\s*(\d+))?',row)) for row in matching):
                errors.append('缺对应报告条目/行号：' + x['id'])
    return errors


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('hits'); p.add_argument('worklist'); p.add_argument('--ledger',required=True)
    a=p.parse_args(); errors=verify(a.hits,a.worklist,a.ledger)
    print('命中处置待完成=%d；台账=%s' % (len(errors),a.ledger))
    for e in errors[:20]: print(e)
    raise SystemExit(2 if errors else 0)
