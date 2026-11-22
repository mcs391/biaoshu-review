#!/usr/bin/env python3
"""Versioned local review inventory/cache and fail-closed completion ledger.
This validates recorded work/evidence, never decides procurement compliance.
"""
import argparse
import hashlib
import json
import posixpath
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

BASE = Path(__file__).resolve().parent.parent
SC = BASE / 'scripts'
STAGES = ['requirements', 'qualification_forms', 'price_math', 'price_groups',
          'cross_documents', 'narrative_vs_list', 'energy', 'certificates',
          'warranty', 'service_times', 'schedule', 'declarations', 'claims', 'final_regression']
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def rules_hash():
    files = [BASE / 'SKILL.md', BASE / 'FOR_AI.md', BASE / 'run_pipeline.py']
    for folder, pattern in [('scripts','*.py'), ('references','*.md'), ('data','*.json')]:
        files += list((BASE / folder).rglob(pattern))
    return hashlib.sha256(''.join(str(p.relative_to(BASE)) + digest(p) for p in sorted(files)).encode()).hexdigest()


def run(script, *args):
    subprocess.run([sys.executable, str(SC / script), *map(str, args)], check=True)


def inventory(source, outdir, stem):
    assets, extra, alerts = [], [], []
    if source.suffix.lower() == '.docx':
        from lxml import etree
        ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        with ZipFile(source) as z:
            trees = {}
            occurrences = {}
            for name in z.namelist():
                if not name.startswith('word/') or not name.endswith('.xml'):
                    continue
                root = etree.fromstring(z.read(name))
                trees[name] = root
                relpath = posixpath.join(posixpath.dirname(name), '_rels', posixpath.basename(name) + '.rels')
                rels = {}
                if relpath in z.namelist():
                    for rel in etree.fromstring(z.read(relpath)):
                        if rel.get('TargetMode') == 'External':
                            alerts.append({'part':name, 'kind':'external_relationship', 'target':rel.get('Target')})
                        else:
                            rels[rel.get('Id')] = posixpath.normpath(posixpath.join(posixpath.dirname(name), rel.get('Target',''))).lstrip('/')
                for node in root.iter():
                    for key, val in node.attrib.items():
                        if key.endswith(('}embed','}id','}link')) and val in rels:
                            occurrences.setdefault(rels[val], []).append({'part':name, 'xpath':root.getroottree().getpath(node)})
                paras = root.xpath('//w:txbxContent//w:p', namespaces=ns) if name == 'word/document.xml' else root.xpath('//w:p', namespaces=ns)
                for p in paras:
                    text = ''.join(p.xpath('.//w:t/text()', namespaces=ns)).strip()
                    if text:
                        extra.append({'part':name, 'xpath':root.getroottree().getpath(p), 'text':text})
                for tag in ['ins','del','altChunk','object','sdt']:
                    nodes = root.xpath('//w:' + tag, namespaces=ns)
                    if nodes:
                        alerts.append({'part':name, 'kind':tag, 'count':len(nodes)})
                nested_tables = root.xpath('//w:tbl//w:tbl', namespaces=ns)
                if nested_tables:
                    alerts.append({'part':name, 'kind':'nested_tables_require_review','count':len(nested_tables)})
                if name.startswith(('word/charts/','word/diagrams/')):
                    alerts.append({'part':name, 'kind':'chart_or_diagram_requires_render_review'})
            for name in z.namelist():
                if name.startswith(('word/media/', 'word/embeddings/')) and not name.endswith('/'):
                    blob = z.read(name)
                    sha = hashlib.sha256(blob).hexdigest()
                    target = outdir / (stem + '.assets') / (sha + Path(name).suffix)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        target.write_bytes(blob)
                    assets.append({'id':name, 'sha256':sha, 'path':str(target.resolve()),
                                   'occurrences':occurrences.get(name, []), 'status':'pending'})
    elif source.suffix.lower() == '.pdf':
        from pypdf import PdfReader
        for i, page in enumerate(PdfReader(source).pages, 1):
            alerts.append({'kind':'pdf_page_visual_review', 'page':i,
                           'text_chars':len(page.extract_text() or '')})
    extra_path = outdir / (stem + '.extra.lines.txt')
    extra_path.write_text(''.join(f"{i}\t[{x['part']} {x['xpath']}] {x['text']}\n" for i,x in enumerate(extra,1)), encoding='utf-8')
    return {'assets':assets, 'alerts':alerts, 'extra_lines':str(extra_path.resolve())}


def prepare(source, outdir, force=False):
    source, outdir = Path(source).resolve(), Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    stem = source.stem
    manifest_path = outdir / (stem + '.document.json')
    fingerprint = {'source':str(source), 'source_sha256':digest(source), 'rules_sha256':rules_hash()}
    if manifest_path.exists() and not force:
        old = read(manifest_path)
        if all(old.get(k) == v for k,v in fingerprint.items()) and all(Path(p).is_file() and digest(p) == h for p,h in old.get('artifacts',{}).items()):
            if old.get('artifacts'):
                print('CACHE HIT: 复用提取及索引；不代表复用审核结论。')
                return old
    run('extract_text.py', source, '--outdir', outdir)
    lines = outdir / (stem + '.lines.txt')
    run('scan_keywords.py', lines)
    run('scan_candidates.py', lines, '--hits', outdir / (stem + '.hits.json'))
    inv = inventory(source, outdir, stem)
    chunks = []
    for channel, p in [('main',lines), ('extra',Path(inv['extra_lines']))]:
        rows = p.read_text(encoding='utf-8').splitlines()
        for a in range(0,len(rows),80):
            chunks.append({'id':f'{channel}:{a+1}-{min(a+80,len(rows))}', 'path':str(p),
                           'start':a+1, 'end':min(a+80,len(rows)),
                           'sha256':hashlib.sha256('\n'.join(rows[a:a+80]).encode()).hexdigest(), 'status':'pending'})
    tables_path = outdir / (stem + '.tables.json')
    paths = [lines, Path(inv['extra_lines']), outdir/(stem+'.hits.json')]
    if tables_path.exists():
        paths.append(tables_path)
    paths += [Path(x['path']) for x in inv['assets']]
    result = dict(fingerprint, schema=1, lines=str(lines), tables=str(tables_path) if tables_path.exists() else None,
                  hits=str(outdir/(stem+'.hits.json')), chunks=chunks, **inv,
                  artifacts={str(p):digest(p) for p in paths})
    save(manifest_path, result)
    return result


def hit_records(hits):
    records = []
    for category, rows in hits.get('hits',{}).items():
        for h in rows:
            identity = json.dumps([category,h.get('line'),h.get('word',h.get('pattern',h.get('mark'))),h.get('item_index')],ensure_ascii=False)
            records.append({'id':hashlib.sha256(identity.encode()).hexdigest()[:20], 'category':category,
                            'line':h['line'], 'text':h.get('text',''), 'status':'pending', 'reason':''})
    return records


def init_review(args):
    out = Path(args.outdir).resolve()
    requested_scope = {'project':args.project,'bidder':args.bidder,'lot':args.lot}
    previous = read(args.previous) if args.previous else None
    if previous and previous.get('scope') != requested_scope:
        raise ValueError('项目/公司/标项不同，拒绝跨主体复用；未建立新审核台账。')
    state_path = out / 'review.json'
    if state_path.exists():
        raise ValueError('review.json 已存在；新版本使用新的目录，保留旧底稿，不覆盖已审状态。')
    inputs = [('tender',args.tender)]
    for entry in args.bid:
        role, sep, file = entry.partition('=')
        if not sep or role not in ('qualification','technical','price','other'):
            raise ValueError('--bid 必须为 qualification/technical/price/other=文件路径')
        inputs.append((role,file))
    docs = {}
    for i,(role,file) in enumerate(inputs):
        key = f'd{i+1}'
        doc = prepare(file, out/key)
        doc['role'] = role
        if role == 'price' and doc['tables']:
            result = out/key/'price_consistency.json'
            run('check_bid_price_consistency.py', doc['tables'], '--out', result)
            doc['price_result'] = str(result)
            doc['price_group_reviews'] = [dict(id=x['id'],status='pending',reason='',evidence=[]) for x in read(result)['repeat_groups']]
        docs[key] = doc
    state = {'schema':1, 'scope':requested_scope,
             'rules_sha256':rules_hash(), 'mode':'preseal_word', 'documents':docs,
             'stages':{s:{'status':'pending','reason':'','evidence':[]} for s in STAGES},
             'hit_dispositions':hit_records(read(docs['d1']['hits'])),
             'requirements':[], 'products':[], 'energy_checks':[], 'issues':[],
             'usage':{'actual_tokens':None,'estimated_tokens':None,'note':'未提供实际用量，不编造节省比例'}}
    save(state_path,state)
    if args.previous:
        changes = compare_reviews(previous,state)
        save(out/'changes.json',changes)
    print('已建立待审台账：',state_path)


def compare_reviews(old, new):
    if old.get('scope') != new.get('scope'):
        raise ValueError('项目/公司/标项不同，不允许跨主体复用审核状态')
    changes = {'rules_changed':old.get('rules_sha256') != new.get('rules_sha256'),
               'note':'仅定位变化；新版本状态仍为pending，关联检查不可省略。', 'documents':[]}
    for key,d in new['documents'].items():
        candidates = [x for x in old['documents'].values() if x.get('role') == d.get('role') and x['source'] == d['source']]
        prior = candidates[0] if len(candidates) == 1 else {}
        previous_chunks = {x['id']:x.get('sha256') for x in prior.get('chunks',[])}
        changes['documents'].append({'doc':key,'same_source_bytes':prior.get('source_sha256') == d['source_sha256'],
                                     'unchanged_chunks':[x['id'] for x in d['chunks'] if x['sha256'] == previous_chunks.get(x['id'])],
                                     'changed_or_new_chunks':[x['id'] for x in d['chunks'] if x['sha256'] != previous_chunks.get(x['id'])],
                                     'removed_chunks':list(set(previous_chunks)-{x['id'] for x in d['chunks']}),
                                     'new_images':[x['id'] for x in d['assets'] if x['sha256'] not in {a['sha256'] for a in prior.get('assets',[])}]})
    return changes


def evidence_ok(ref, docs):
    if not isinstance(ref,dict) or ref.get('doc') not in docs:
        return False
    doc = docs[ref['doc']]
    if 'asset' in ref:
        return any(x['id'] == ref['asset'] for x in doc['assets']) and bool(ref.get('quote'))
    channel = ref.get('channel','main')
    path = doc['lines'] if channel == 'main' else doc['extra_lines'] if channel == 'extra' else None
    if not path:
        return False
    rows = Path(path).read_text(encoding='utf-8').splitlines()
    a,b = ref.get('start'),ref.get('end',ref.get('start'))
    if not isinstance(a,int) or not isinstance(b,int) or not 1 <= a <= b <= len(rows):
        return False
    # A verbatim excerpt is required, not only a fabricated line number.
    raw = '\n'.join(r.split('\t',1)[-1] for r in rows[a-1:b])
    return bool(ref.get('quote')) and ref['quote'] in raw


def validate(state):
    errors = []
    docs = state.get('documents',{})
    if state.get('rules_sha256') != rules_hash():
        errors.append('审核规则已变化，需新建版本并复核')
    if not docs or not any(d.get('role') == 'tender' for d in docs.values()):
        errors.append('缺少招标文件')
    for key,d in docs.items():
        manifest_path = Path(d['lines']).with_name(Path(d['lines']).name.replace('.lines.txt','.document.json'))
        if not manifest_path.is_file():
            errors.append(key + ':缺原始内容索引')
        else:
            original = read(manifest_path)
            for field in ['source','source_sha256','rules_sha256','lines','tables','hits','extra_lines','artifacts']:
                if d.get(field) != original.get(field):
                    errors.append(key + ':固定索引字段被改动 ' + field)
            for field in ['chunks','assets','alerts']:
                def fixed(x):
                    return {k:v for k,v in x.items() if k not in ('status','reason')}
                if [fixed(x) for x in d.get(field,[])] != [fixed(x) for x in original.get(field,[])]:
                    errors.append(key + ':内容索引遗漏/变更 ' + field)
        if not Path(d['source']).is_file() or digest(d['source']) != d['source_sha256']:
            errors.append(key + ':源文件已变化或丢失')
        for p,h in d['artifacts'].items():
            if not Path(p).is_file() or digest(p) != h:
                errors.append(key + ':提取/图片产物失效 ' + p)
        for x in d['chunks'] + d['assets']:
            if x.get('status') not in ('reviewed','excluded') or not x.get('reason'):
                errors.append(key + ':内容未处置 ' + x['id'])
        for x in d['alerts']:
            if x.get('status') != 'reviewed' or not x.get('reason'):
                errors.append(key + ':特殊内容待核 ' + x['kind'])
        if d.get('role') == 'price':
            p = d.get('price_result')
            if not p or not Path(p).is_file():
                errors.append(key + ':缺报价反向归组结果')
            else:
                result = read(p)
                # Recompute deterministic findings: do not trust a hand-edited result file.
                import check_bid_price_consistency as price
                diagnostics = {}
                parsed = price.extract_items(read(d['tables']),diagnostics)
                complete = bool(parsed) and not diagnostics['skipped_rows'] and not diagnostics['unrecognized_tables']
                if result.get('items_scanned') != len(parsed) or result.get('findings') != price.analyze(parsed) or result.get('complete') != complete:
                    errors.append(key + ':报价结果与源表格不符')
                groups = {x['id'] for x in price.repeat_groups(parsed)}
                reviews = {x['id']:x for x in d.get('price_group_reviews',[])}
                if groups != set(reviews):
                    errors.append(key + ':重复型号逐组台账不全')
                for id in groups:
                    row = reviews.get(id,{})
                    if row.get('status') != 'reviewed' or not row.get('reason') or not row.get('evidence') or not all(evidence_ok(e,docs) for e in row['evidence']):
                        errors.append(key + ':重复型号组未核 ' + id)
                if result.get('tables_sha256') != digest(d['tables']):
                    errors.append(key + ':报价结果版本不符')
                if not result.get('complete'):
                    proof = d.get('manual_price_coverage',{})
                    expected = proof.get('expected')
                    if not isinstance(expected,int) or expected <= 0 or expected != proof.get('reviewed') or not proof.get('reason') or not proof.get('evidence') or not all(evidence_ok(e,docs) for e in proof['evidence']):
                        errors.append(key + ':报价解析不全，缺人工逐行对账证据')
    for stage in STAGES:
        entry = state.get('stages',{}).get(stage,{})
        if entry.get('status') not in ('done','not_applicable') or not entry.get('reason') or not entry.get('evidence') or not all(evidence_ok(e,docs) for e in entry['evidence']):
            errors.append('专项未完成或证据无效：' + stage)
    tender = next((d for d in docs.values() if d.get('role') == 'tender'),None)
    if tender:
        expected = {h['id'] for h in hit_records(read(tender['hits']))}
        actual = {h.get('id'):h for h in state.get('hit_dispositions',[])}
        if expected != set(actual):
            errors.append('命中台账不全或存在过期命中')
        for id in expected:
            x = actual.get(id,{})
            if x.get('status') not in ('included','excluded','duplicate') or not x.get('reason'):
                errors.append('命中未处置：' + id)
    requirements = state.get('requirements',[])
    if not requirements:
        errors.append('缺招标要求与投标响应逐项台账')
    for x in requirements:
        if x.get('status') not in ('matched','risk','not_applicable','unverified') or not evidence_ok(x.get('tender'),docs) or not x.get('reason'):
            errors.append('要求缺状态/招标证据：' + str(x.get('id')))
        if x.get('status') == 'matched' and not evidence_ok(x.get('bid'),docs):
            errors.append('匹配结论缺投标证据：' + str(x.get('id')))
        if x.get('status') == 'unverified':
            errors.append('要求尚未核实：' + str(x.get('id')))
    products = state.get('products',[])
    energy = {x.get('product_id'):x for x in state.get('energy_checks',[])}
    if len({p.get('id') for p in products}) != len(products):
        errors.append('产品ID重复')
    for p in products:
        if p.get('energy_applicability') not in ('required','not_required') or not p.get('basis') or not evidence_ok(p.get('evidence'),docs):
            errors.append('产品节能适用性未核：' + str(p.get('id')))
        if p.get('energy_applicability') == 'required':
            e = energy.get(p['id'],{})
            if e.get('status') not in ('matched','not_found') or not e.get('reason') or not e.get('evidence') or not all(evidence_ok(r,docs) for r in e['evidence']):
                errors.append('节能型号未核：' + p['id'])
            if e.get('status') == 'matched':
                if p.get('model') not in e.get('certificate_models',[]) or not e.get('certificate_number') or not e.get('scope_checked') or not e.get('validity_checked') or not e.get('original_image_reviewed'):
                    errors.append('节能匹配缺精确型号/原图/范围/有效期核验：' + p['id'])
                refs = e.get('evidence',[])
                if not any('asset' in r and any(a['id'] == r['asset'] and a.get('status') == 'reviewed' for a in docs.get(r.get('doc'),{}).get('assets',[])) for r in refs):
                    errors.append('节能匹配没有已核原图证据：' + p['id'])
    if not products and state.get('stages',{}).get('energy',{}).get('status') != 'not_applicable':
        errors.append('缺产品清单，不能宣称节能全量核对')
    for issue in state.get('issues',[]):
        if not issue.get('reason') or not issue.get('evidence') or not all(evidence_ok(e,docs) for e in issue['evidence']):
            errors.append('问题缺原文证据：' + str(issue.get('id')))
    return errors


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd',required=True)
    p = sub.add_parser('prepare'); p.add_argument('source'); p.add_argument('--outdir',required=True); p.add_argument('--force',action='store_true')
    p = sub.add_parser('init'); p.add_argument('tender'); p.add_argument('--bid',action='append',default=[])
    p.add_argument('--previous',help='可选：同项目/公司/标项上一轮review.json，仅生成差异索引')
    for name in ['outdir','project','bidder','lot']:
        p.add_argument('--'+name,required=True)
    p = sub.add_parser('verify'); p.add_argument('state')
    args = ap.parse_args()
    if args.cmd == 'prepare':
        prepare(args.source,args.outdir,args.force)
    elif args.cmd == 'init':
        init_review(args)
    else:
        state = read(args.state)
        errors = validate(state)
        result = {'status':'incomplete' if errors else 'review_complete_not_compliance_approval',
                  'errors':errors, 'issue_count':len(state.get('issues',[]))}
        save(Path(args.state).with_suffix('.verification.json'),result)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        raise SystemExit(2 if errors else 0)


if __name__ == '__main__':
    main()
