"""Synthetic regressions for missed bids, evidence gates and extraction cache.
No customer artifacts, network or live bid modification.
"""
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASE=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(BASE/'scripts'))
import review_state as r
import scan_keywords as scan
import check_bid_price_consistency as price
import check_hit_dispositions as gate


def table(rows):
    return [{'table_id':1,'line_start':1,'rows':[['产品名称','品牌','型号','单位','单价','数量','合计（元）'],*rows]}]


class Regression(unittest.TestCase):
    def test_chapter_reference_not_filtered(self):
        kw=r.read(BASE/'data/keywords.json')
        for text in ['投标人须按第三章要求提供证明，否则投标无效。','第三章规定材料缺失按无效投标处理']:
            self.assertTrue(scan.scan([(1,text)],kw)[0]['primary'])

    def test_factory_report_not_filtered(self):
        h=scan.scan([(1,'须提供原厂出具的检测报告。')],r.read(BASE/'data/keywords.json'))[0]
        self.assertTrue(h['certifications'])

    def test_cross_name_and_unit_prices(self):
        items=price.extract_items(table([['杀虫','塞恩','SE-815-3','套','700','30','21000'],['气象','塞恩','SE-815-3','台','900','4','3600']]))
        findings=price.analyze(items)
        self.assertEqual(len(findings),1)
        self.assertEqual(findings[0]['risk'],'high_cross_unit_same_model')

    def test_partial_parse_not_complete(self):
        diag={}; items=price.extract_items(table([['A','品牌','X','台','100','1','100'],['B','','X','台','200','1','200']]),diag)
        self.assertEqual(len(items),1); self.assertEqual(diag['candidate_rows'],2)
        self.assertEqual(len(diag['skipped_rows']),1)

    def test_custom_model_needs_manual_review(self):
        diag={}; price.extract_items(table([['定制屏','品牌','定制','项','100','1','100']]),diag)
        self.assertEqual(len(diag['skipped_rows']),1)

    def test_price_not_first_number_of_range(self):
        self.assertIsNone(price.parse_decimal('100-200'))
        self.assertEqual(str(price.parse_decimal('1,000.00元')),'1000.00')

    def test_same_price_not_flagged(self):
        items=price.extract_items(table([['A','品牌','X','台','100','1','100'],['B','品牌','X','套','100','2','200']]))
        self.assertEqual(price.analyze(items),[])
        self.assertEqual(len(price.repeat_groups(items)),1)

    def test_cross_bidder_diff_refused(self):
        old={'scope':{'project':'A','bidder':'甲','lot':'1'}}
        new={'scope':{'project':'A','bidder':'乙','lot':'1'}}
        with self.assertRaises(ValueError): r.compare_reviews(old,new)

    def test_changed_chunks_not_auto_approved(self):
        scope={'project':'A','bidder':'甲','lot':'1'}
        doc={'role':'technical','source':'same.docx','source_sha256':'old','chunks':[{'id':'main:1-80','sha256':'old','status':'reviewed'}],'assets':[]}
        old={'scope':scope,'rules_sha256':'r','documents':{'d1':doc}}
        new=copy.deepcopy(old); new['documents']['d1']['chunks'][0].update(sha256='new',status='pending')
        changes=r.compare_reviews(old,new)
        self.assertEqual(changes['documents'][0]['changed_or_new_chunks'],['main:1-80'])
        self.assertEqual(new['documents']['d1']['chunks'][0]['status'],'pending')

    def test_fixed_units_scope_explanation(self):
        items=price.extract_items(table([['屏2.5平方米','品牌','P10','项','13500','1','13500'],['屏5平方米','品牌','P10','项','15000','1','15000']]))
        self.assertEqual(price.analyze(items)[0]['risk'],'needs_scope_explanation')

    def test_disposition_gate_and_new_hits(self):
        with tempfile.TemporaryDirectory(prefix='bid_v3_') as d:
            p=Path(d); lines=p/'s.lines.txt'; lines.write_text('1\t否则投标无效\n2\t必须提供原厂授权\n',encoding='utf-8')
            hp=p/'h.json'; md=p/'w.md'; ledger=p/'ledger.json'
            r.save(hp,{'source':str(lines),'hits':{'primary':[{'line':1,'word':'无效','text':'否则投标无效'}]}})
            md.write_text('## 商务线·废标\n| ID | 出处 |\n| B-D1 | 行1 |\n',encoding='utf-8')
            self.assertTrue(gate.verify(hp,md,ledger))
            data=r.read(ledger); data['items'][0].update(status='included',reason='已列原文',report_id='B-D1'); r.save(ledger,data)
            self.assertEqual(gate.verify(hp,md,ledger),[])
            data=r.read(hp); data['hits']['customization']=[{'line':2,'word':'原厂授权','text':'必须提供原厂授权'}]; r.save(hp,data)
            self.assertTrue(gate.verify(hp,md,ledger))

    def make_document(self,p):
        from docx import Document
        from lxml import etree
        doc=Document(); doc.add_paragraph('本项目要求投标文件完整响应采购需求，未提供必要材料按无效投标处理。所有证据应当清晰可辨并且与所投产品对应。')
        # Hidden text box content is separately inventoried, not silently lost.
        para=doc.add_paragraph()
        para._p.append(etree.fromstring('<w:txbxContent xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>补充文本型号X-1</w:t></w:r></w:p></w:txbxContent>'))
        doc.save(p)

    def test_prepare_cache_and_stale_rejection(self):
        with tempfile.TemporaryDirectory(prefix='bid_v3_') as d:
            p=Path(d); src=p/'sample.docx'; self.make_document(src)
            doc=r.prepare(src,p/'out')
            stamp=Path(doc['lines']).stat().st_mtime_ns
            again=r.prepare(src,p/'out')
            self.assertEqual(Path(again['lines']).stat().st_mtime_ns,stamp)
            self.assertIn('补充文本型号X-1',Path(doc['extra_lines']).read_text(encoding='utf-8'))
            state=self.completed_state(doc)
            self.assertEqual(r.validate(state),[])
            broken=copy.deepcopy(state); broken['documents']['d1']['chunks']=[]
            self.assertTrue(any('内容索引' in x for x in r.validate(broken)))
            src.write_bytes(src.read_bytes()+b'changed')
            self.assertTrue(any('源文件已变化' in x for x in r.validate(state)))

    def completed_state(self,doc):
        doc=copy.deepcopy(doc); doc['role']='tender'
        quote=Path(doc['lines']).read_text(encoding='utf-8').splitlines()[0].split('\t',1)[1]
        ev={'doc':'d1','start':1,'quote':quote}
        for x in doc['chunks']+doc['assets']+doc['alerts']: x.update(status='reviewed',reason='合成样例逐项检查')
        hits=r.hit_records(r.read(doc['hits']))
        for x in hits: x.update(status='included',reason='已入要求台账')
        return {'rules_sha256':r.rules_hash(),'documents':{'d1':doc},
                'stages':{k:{'status':'not_applicable','reason':'合成测试限定范围','evidence':[ev]} for k in r.STAGES},
                'hit_dispositions':hits,'requirements':[{'id':'R1','status':'matched','reason':'测试响应','tender':ev,'bid':ev}],
                'products':[],'energy_checks':[],'issues':[]}

    def test_energy_suffix_and_image_evidence_gate(self):
        with tempfile.TemporaryDirectory(prefix='bid_v3_') as d:
            p=Path(d); src=p/'s.docx'; self.make_document(src)
            state=self.completed_state(r.prepare(src,p/'out'))
            ev=state['requirements'][0]['tender']
            state['products']=[{'id':'P1','model':'LP-D55-A','energy_applicability':'required','basis':'测试范围','evidence':ev}]
            state['energy_checks']=[{'product_id':'P1','status':'matched','reason':'测试','evidence':[ev],
                                    'certificate_models':['LP-D55'],'certificate_number':'TEST','scope_checked':True,
                                    'validity_checked':True,'original_image_reviewed':True}]
            errors=r.validate(state)
            self.assertTrue(any('精确型号' in x for x in errors))
            self.assertTrue(any('原图证据' in x for x in errors))

    def test_unverified_requirements_never_complete(self):
        with tempfile.TemporaryDirectory(prefix='bid_v3_') as d:
            p=Path(d); src=p/'s.docx'; self.make_document(src)
            state=self.completed_state(r.prepare(src,p/'out'))
            state['requirements'][0]['status']='unverified'
            self.assertTrue(any('尚未核实' in x for x in r.validate(state)))

    def test_missing_pipeline_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix='bid_v3_') as d:
            p=Path(d); md=p/'s.工作区.md'; md.write_text('# 空测试',encoding='utf-8')
            result=subprocess.run([sys.executable,str(BASE/'run_pipeline.py'),'verify',str(md)],capture_output=True)
            self.assertNotEqual(result.returncode,0); self.assertFalse((p/'s.xlsx').exists())

    def test_pipeline_dispositions_required_then_export(self):
        with tempfile.TemporaryDirectory(prefix='bid_v3_') as d:
            p=Path(d); src=p/'s.docx'; self.make_document(src)
            doc=r.prepare(src,p/'out'); md=p/'out'/'s.工作区.md'
            md.write_text('## 商务线·废标\n| ID | 条款 | 出处 |\n|---|---|---|\n| B-D1 | 原文要求 | 行1 |\n',encoding='utf-8')
            cmd=[sys.executable,str(BASE/'run_pipeline.py'),'verify',str(md)]
            first=subprocess.run(cmd,capture_output=True)
            self.assertNotEqual(first.returncode,0); self.assertFalse((p/'out'/'s.xlsx').exists())
            ledger=p/'out'/'s.dispositions.json'; data=r.read(ledger)
            for item in data['items']: item.update(status='included',reason='合成原文要求已列',report_id='B-D1')
            r.save(ledger,data)
            second=subprocess.run(cmd,capture_output=True)
            self.assertEqual(second.returncode,0,second.stdout.decode('utf-8',errors='replace')+second.stderr.decode('utf-8',errors='replace'))
            self.assertTrue((p/'out'/'s.xlsx').exists())

    def test_embedded_image_preserved_and_indexed(self):
        import base64
        from docx import Document
        with tempfile.TemporaryDirectory(prefix='bid_v3_') as d:
            p=Path(d); src=p/'s.docx'; self.make_document(src)
            doc=Document(src)
            blob=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1f8AAAAASUVORK5CYII=')
            doc.add_picture(io.BytesIO(blob)); doc.save(src)
            index=r.prepare(src,p/'out')
            self.assertEqual(len(index['assets']),1)
            asset=index['assets'][0]
            self.assertEqual(Path(asset['path']).read_bytes(),blob)
            self.assertTrue(asset['occurrences'])
            self.assertEqual(asset['status'],'pending')

    def test_bid_init_wires_price_checks_and_blocks_incomplete(self):
        from docx import Document
        with tempfile.TemporaryDirectory(prefix='bid_v3_') as d:
            p=Path(d); src=p/'tender.docx'; self.make_document(src)
            bid=p/'quote.docx'; doc=Document(src)
            rows=table([['设备A','测试品牌','X1','台','100','2','201'],['设备B','测试品牌','X1','套','200','1','200']])[0]['rows']
            t=doc.add_table(rows=0,cols=7)
            for vals in rows:
                cells=t.add_row().cells
                for i,v in enumerate(vals): cells[i].text=v
            doc.save(bid)
            out=p/'review'
            cmd=[sys.executable,str(BASE/'run_pipeline.py'),'bid-init',str(src),'--bid','price='+str(bid),'--project','TEST','--bidder','TEST','--lot','1','--outdir',str(out)]
            result=subprocess.run(cmd,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))
            state=r.read(out/'review.json'); price_doc=state['documents']['d2']; facts=r.read(price_doc['price_result'])
            self.assertEqual(facts['different_price_groups'],1)
            self.assertEqual(facts['arithmetic'][0]['status'],'mismatch')
            self.assertEqual(len(price_doc['price_group_reviews']),1)
            self.assertTrue(r.validate(state))


if __name__=='__main__': unittest.main(verbosity=2)
