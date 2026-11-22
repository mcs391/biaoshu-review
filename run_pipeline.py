#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_pipeline.py — 一键串联程序步骤，让 AI agent 只需专注判断

阶段：
  prep       — 取数、图片清点、分块索引、扫描和缓存
  verify     — 全命中处置 + 可选投标台账关卡 + Excel
  bid-init   — 建立签章前多文件审核台账（--bid role=路径）
  bid-verify — 检查台账版本、覆盖及证据，不判断投标有效性

用法：
  python run_pipeline.py prep   <招标文件.docx/.pdf> [--outdir workspace]
  python run_pipeline.py verify <工作区.md> [--out 输出.xlsx]

示例（用自带测试样本跑通全流程）：
  python run_pipeline.py prep   tests/fixtures/sample_tender.docx
  python run_pipeline.py verify workspace/sample_tender.工作区.md
"""
import sys
import subprocess
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPTS = Path(__file__).resolve().parent / "scripts"


def run(cmd, label):
    print("\n" + "=" * 60)
    print("▶ %s" % label)
    print("  %s" % " ".join(str(c) for c in cmd))
    print("-" * 60)
    r = subprocess.run([sys.executable] + [str(c) for c in cmd])
    if r.returncode != 0:
        print("✗ %s 失败 (exit %d)" % (label, r.returncode))
        return False
    return True


def prep(tender_file, outdir):
    # Shared extraction/index/cache; run no duplicate prep when input and rules are unchanged.
    ok = run([SCRIPTS / 'review_state.py', 'prepare', tender_file, '--outdir', outdir],
             '取数、索引、图片清点与版本缓存')
    if not ok:
        sys.exit(1)
    print('下一步：读取原文与索引，建立工作区；verify 会要求逐项处置台账。')
    return


def verify(worklist_file, out_xlsx, review=None):
    worklist = Path(worklist_file)
    if not worklist.exists():
        print("✗ 工作区文件不存在: %s" % worklist)
        print("  请先让 AI agent 按 SKILL.md 步骤 1-2-4-5 写完工作区 md")
        sys.exit(1)

    ws_dir = worklist.parent
    stem = worklist.stem.replace(".工作区", "")
    hits_file = ws_dir / (stem + ".hits.json")

    lines_file = ws_dir / (stem + ".lines.txt")
    if not lines_file.exists() or not hits_file.exists():
        print('✗ 缺少当前版本 lines/hits，不能跳过防漏检查。先运行 prep。')
        sys.exit(1)
    manifest = ws_dir / (stem + '.document.json')
    if not manifest.exists():
        print('✗ 缺版本索引，请对当前源文件重新运行 prep。')
        sys.exit(1)
    sys.path.insert(0, str(SCRIPTS))
    from review_state import read, digest, rules_hash
    meta = read(manifest)
    if meta.get('rules_sha256') != rules_hash() or not Path(meta['source']).exists() or digest(meta['source']) != meta['source_sha256'] or any(not Path(p).is_file() or digest(p) != h for p,h in meta['artifacts'].items()):
        print('✗ 源文件、规则或提取结果已变化；请重新 prep 并复核，不沿用旧结论。')
        sys.exit(1)
    harvest_args = [SCRIPTS / "harvest_ai_words.py", str(worklist)]
    if lines_file.exists():
        harvest_args += ["--lines", str(lines_file)]
    ok = run(harvest_args,
             "Step 5+ · 收割 + 补扫：AI 发现的疑似判词 → 候选库 + 回扫当前标书")
    if not ok:
        print("✗ verify 中止：新词收割/补扫失败，未生成 Excel。")
        sys.exit(1)

    if hits_file.exists():
        rescan = ws_dir / (stem + '.ai_rescan.hits.json')
        if not rescan.exists():
            print('✗ 缺本轮补扫结果。')
            sys.exit(1)
        hits_file = rescan
        ok = run([SCRIPTS/'check_hit_dispositions.py',hits_file,worklist,
                  '--ledger',ws_dir/(stem+'.dispositions.json')], '全类别逐项处置关卡（含补扫）')
        if not ok:
            print('✗ 存在未处置命中；请填写台账并补齐报告。未生成完成版Excel。')
            sys.exit(1)
        print('✓ 原始及补扫命中已逐项处置；不以条数阈值替代检查。')
    else:
        sys.exit('缺少命中结果，禁止跳过护栏')

    explicit_review = review is not None
    review = Path(review) if explicit_review else ws_dir/'review.json'
    if not explicit_review and not review.exists() and (ws_dir.parent/'review.json').exists():
        review = ws_dir.parent/'review.json'
    if explicit_review and not review.exists():
        sys.exit('指定review台账不存在，禁止跳过投标文件完成关卡')
    if review.exists():
        if not run([SCRIPTS/'review_state.py','verify',review], '投标文件全量审核完成关卡'):
            sys.exit(1)

    if not out_xlsx:
        out_xlsx = str(ws_dir / (stem + ".xlsx"))

    ok = run([SCRIPTS / "build_excel.py", out_xlsx, str(worklist)],
             "Step 7 · 出 Excel")
    if not ok:
        print("✗ verify 中止：Excel 生成失败。")
        sys.exit(1)

    print('✓ 报告已生成；这不是投标有效性或无风险保证。')
    print('  Excel:', out_xlsx)
    print('  判词持久入库和对外上传均需单独授权；本流程不自动执行。')


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('bid-init','bid-verify'):
        command = 'init' if sys.argv[1] == 'bid-init' else 'verify'
        sys.exit(subprocess.call([sys.executable,str(SCRIPTS/'review_state.py'),command,*sys.argv[2:]]))
    if len(sys.argv) < 3 or sys.argv[1] not in ("prep", "verify"):
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "prep":
        outdir = "workspace"
        rest = sys.argv[2:]
        for i, a in enumerate(rest):
            if a == "--outdir" and i + 1 < len(rest):
                outdir = rest[i + 1]
                rest = rest[:i] + rest[i + 2:]
                break
        if not rest:
            print("用法: python run_pipeline.py prep <招标文件> [--outdir workspace]")
            sys.exit(1)
        prep(rest[0], outdir)

    elif cmd == "verify":
        out = None
        rest = sys.argv[2:]
        review = None
        if '--review' in rest:
            i = rest.index('--review')
            review = rest[i+1]
            rest = rest[:i]+rest[i+2:]
        for i, a in enumerate(rest):
            if a == "--out" and i + 1 < len(rest):
                out = rest[i + 1]
                rest = rest[:i] + rest[i + 2:]
                break
        if not rest:
            print("用法: python run_pipeline.py verify <工作区.md> [--out 输出.xlsx]")
            sys.exit(1)
        verify(rest[0], out, review)


if __name__ == "__main__":
    main()
