#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两层反向归组，检查报价表内部同型号异价。

第一层按“品牌+型号”强制归组，不因单位或名称不同而跳过；
第二层按“品牌+型号+单位”辅助归组，用于解释计价范围。

输入为 extract_text.py 生成的 *.tables.json。程序只列确定性事实，
不把异价直接判为废标；AI 需回查技术配置和招标条款。

用法:
    python scripts/check_bid_price_consistency.py 报价文件.tables.json
    python scripts/check_bid_price_consistency.py 报价文件.tables.json --out result.json
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


BRAND_HEADERS = {"品牌", "投标品牌"}
MODEL_HEADERS = {"型号", "型号规格", "规格型号"}
UNIT_HEADERS = {"单位", "计量单位"}
PRICE_HEADERS = {"单价", "单价(元)", "单价（元）", "投标单价", "含税单价"}
NAME_HEADERS = {"产品名称", "货物名称", "设备名称", "标的名称", "名称"}
PLACEHOLDER_MODELS = {"", "-", "—", "/", "无", "不适用", "定制"}
AGGREGATE_UNITS = {"批", "项", "宗"}


def norm(value):
    return re.sub(r"\s+", "", str('' if value is None else value)).strip()


def header_index(row, names):
    for i, value in enumerate(row):
        text = norm(value)
        if text in names:
            return i
    return None


def parse_decimal(value):
    text = norm(value).replace(",", "").replace("￥", "").replace("¥", "")
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)(?:元)?", text)
    if not match:
        return None
    try:
        return Decimal(match.group(1))
    except InvalidOperation:
        return None


def decimal_text(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def find_price_tables(tables):
    found = []
    for table in tables:
        rows = table.get("rows") or []
        for header_row_index, row in enumerate(rows):
            brand_i = header_index(row, BRAND_HEADERS)
            model_i = header_index(row, MODEL_HEADERS)
            unit_i = header_index(row, UNIT_HEADERS)
            price_i = header_index(row, PRICE_HEADERS)
            if None in (brand_i, model_i, unit_i, price_i):
                continue
            name_candidates = [
                i for i, value in enumerate(row)
                if norm(value) in NAME_HEADERS and i < brand_i
            ]
            name_i = max(name_candidates) if name_candidates else (brand_i - 1 if brand_i > 0 else None)
            found.append(
                {
                    "table_id": table.get("table_id"),
                    "line_start": table.get("line_start"),
                    "rows": rows,
                    "header_row_index": header_row_index,
                    "brand_i": brand_i,
                    "model_i": model_i,
                    "unit_i": unit_i,
                    "price_i": price_i,
                    "name_i": name_i,
                    "quantity_i": header_index(row, {'数量','投标数量'}),
                    "amount_i": header_index(row, {'合价','合计','合计(元)','合计（元）','金额','金额(元)','金额（元）','总价(元)','总价（元）'}),
                }
            )
            break
    return found


def extract_items(tables, diagnostics=None):
    items = []
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.update(candidate_rows=0, skipped_rows=[], excluded_rows=[], unrecognized_tables=[])
    recognized = find_price_tables(tables)
    recognized_ids = {x['table_id'] for x in recognized}
    for table in tables:
        if table.get('table_id') not in recognized_ids:
            diagnostics['unrecognized_tables'].append(table.get('table_id'))
    logical_index = 0
    for info in recognized:
        rows = info["rows"]
        max_i = max(info["brand_i"], info["model_i"], info["unit_i"], info["price_i"])
        for row_offset, row in enumerate(rows[info["header_row_index"] + 1 :], start=1):
            loc = {'table_id': info['table_id'], 'row': info['header_row_index'] + row_offset + 1,
                   'line': (info['line_start'] or 0) + info['header_row_index'] + row_offset}
            if not any(norm(v) for v in row):
                diagnostics['excluded_rows'].append(dict(loc, reason='blank'))
                continue
            if header_index(row, PRICE_HEADERS) is not None and header_index(row, MODEL_HEADERS) is not None:
                diagnostics['excluded_rows'].append(dict(loc, reason='repeated_header'))
                continue
            if any(norm(v) in {'合计','总计','总价','小计','合计金额','总报价'} for v in row[:max_i + 1]):
                diagnostics['excluded_rows'].append(dict(loc, reason='total_requires_arithmetic_review'))
                continue
            diagnostics['candidate_rows'] += 1
            if len(row) <= max_i:
                diagnostics['skipped_rows'].append(dict(loc, reason='short_row', values=row))
                continue
            brand = norm(row[info["brand_i"]])
            model = norm(row[info["model_i"]])
            unit = norm(row[info["unit_i"]])
            price = parse_decimal(row[info["price_i"]])
            if not brand or not unit or price is None or model in PLACEHOLDER_MODELS:
                diagnostics['skipped_rows'].append(dict(loc, reason='missing_or_placeholder_field', values=row))
                continue
            logical_index += 1
            name = norm(row[info["name_i"]]) if info["name_i"] is not None and len(row) > info["name_i"] else ""
            items.append(
                {
                    "item": logical_index,
                    "table_id": info["table_id"],
                    "row": info["header_row_index"] + row_offset + 1,
                    "line": (info["line_start"] or 0) + info["header_row_index"] + row_offset,
                    "name": name,
                    "brand": brand,
                    "model": model,
                    "unit": unit,
                    "unit_price": decimal_text(price),
                    "_price": price,
                }
            )
            for label in ('quantity','amount'):
                idx = info[label + '_i']
                val = parse_decimal(row[idx]) if idx is not None and idx < len(row) else None
                items[-1][label] = decimal_text(val) if val is not None else None
    return items


def analyze(items, include_unit=False):
    grouped = defaultdict(list)
    for item in items:
        if item["model"] in PLACEHOLDER_MODELS:
            continue
        key = (item["brand"].casefold(), item["model"].casefold())
        if include_unit:
            key += (item["unit"],)
        grouped[key].append(item)

    findings = []
    for group in grouped.values():
        prices = sorted({item["_price"] for item in group})
        if len(prices) < 2:
            continue
        public_items = [{k: v for k, v in item.items() if k != "_price"} for item in group]
        minimum = min(prices)
        maximum = max(prices)
        units = sorted({item["unit"] for item in group})
        findings.append(
            {
                "brand": group[0]["brand"],
                "model": group[0]["model"],
                "unit": group[0]["unit"] if len(units) == 1 else None,
                "units": units,
                "prices": [decimal_text(v) for v in prices],
                "price_gap": decimal_text(maximum - minimum),
                "max_min_ratio": decimal_text(
                    (maximum / minimum).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                )
                if minimum > 0
                else None,
                "distinct_names": sorted({item["name"] for item in group if item["name"]}),
                "risk": (
                    "high_cross_unit_same_model"
                    if len(units) > 1
                    else (
                        "needs_scope_explanation"
                        if group[0]["unit"] in AGGREGATE_UNITS
                        else "high"
                    )
                ),
                "items": public_items,
            }
        )
    return findings


def repeat_groups(items):
    """All repeated models, including equal prices: configuration may still conflict."""
    import hashlib
    groups = defaultdict(list)
    for item in items:
        groups[(item['brand'].casefold(),item['model'].casefold())].append({k:v for k,v in item.items() if k != '_price'})
    out=[]
    for key, rows in groups.items():
        if len(rows)>1:
            out.append({'id':hashlib.sha256(json.dumps([key,rows],ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:20],
                        'brand':rows[0]['brand'],'model':rows[0]['model'],'items':rows})
    return out


def main():
    parser = argparse.ArgumentParser(description="两层检查报价表内部同品牌同型号异价")
    parser.add_argument("tables_json", help="extract_text.py 生成的 *.tables.json")
    parser.add_argument("--out", help="可选：保存 JSON 结果")
    parser.add_argument("--strict", action="store_true", help="发现异价组时以非零码退出")
    args = parser.parse_args()

    source = Path(args.tables_json)
    with source.open(encoding="utf-8") as handle:
        tables = json.load(handle)

    diagnostics = {}
    items = extract_items(tables, diagnostics)
    findings = analyze(items)
    same_unit_findings = analyze(items, include_unit=True)
    result = {
        "source": str(source),
        "items_scanned": len(items),
        "complete": bool(items) and not diagnostics['skipped_rows'] and not diagnostics['unrecognized_tables'],
        "coverage": diagnostics,
        "tables_sha256": __import__('hashlib').sha256(source.read_bytes()).hexdigest(),
        "different_price_groups": len(findings),
        "findings": findings,
        "repeat_groups": repeat_groups(items),
        "same_brand_model_unit_different_price_groups": len(same_unit_findings),
        "same_brand_model_unit_findings": same_unit_findings,
        "interpretation": "异价是复核线索，不等同于自动废标；需回查技术配置、计价范围及招标条款。",
    }
    result['arithmetic'] = []
    for item in items:
        rec = {'line':item['line'],'table_id':item['table_id'],'status':'unparsed'}
        if item['quantity'] is not None and item['amount'] is not None:
            expected = (Decimal(item['quantity']) * item['_price']).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
            rec.update(expected=decimal_text(expected),actual=item['amount'],status='matched' if expected == Decimal(item['amount']) else 'mismatch')
        result['arithmetic'].append(rec)
    result['arithmetic_note'] = '仅为行乘积检查；分项累计、总价、大写、限价及报价修正规则仍须独立核对。'

    print(f"报价项={len(items)}，同品牌+型号异价组={len(findings)}")
    if not items:
        print(
            "\n⚠ 未扫描到同时含品牌、型号、单位和单价的报价项。"
            "这不代表价格一致；若报价表无品牌/型号列，"
            "必须与商务货物清单、技术响应按顺序联接后再做两层归组。"
        )
    for finding in findings:
        print(
            f"\n[{finding['risk']}] {finding['brand']}/{finding['model']} "
            f"单位={','.join(finding['units'])} "
            f"单价={','.join(finding['prices'])} 差额={finding['price_gap']} "
            f"倍数={finding['max_min_ratio'] or 'N/A'}"
        )
        for item in finding["items"]:
            print(
                f"  第{item['item']}项 {item['name']} "
                f"单位={item['unit']} 单价={item['unit_price']}"
            )
    if result['complete'] and not findings:
        print("\n✓ 第一层未发现同品牌同型号异价。")
    if not result['complete']:
        print('⚠ 解析未完整覆盖所有表格/行；必须处置未识别表格、缺失字段、定制型号，不得报告全量通过。')
    print(
        f"\n第二层同品牌+型号+单位异价组={len(same_unit_findings)}"
    )
    print("\n提示：异价本身不自动等于废标；必须回查产品配置、报价修正和澄清条款。")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
        print(f"out={out}")

    if args.strict:
        if not result['complete']:
            raise SystemExit(3)
        if findings:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
