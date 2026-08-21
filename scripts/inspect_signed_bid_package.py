#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspect structural properties of final signed bid PDFs.

This script does not validate certificate trust chains or procurement-platform
upload/decryption state. It reports deterministic local facts only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalise_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def analyse_byte_range(value, file_size: int) -> dict:
    try:
        numbers = [int(item) for item in list(value)]
    except Exception:
        numbers = []
    valid_shape = len(numbers) == 4 and all(item >= 0 for item in numbers)
    end = numbers[2] + numbers[3] if valid_shape else None
    return {
        "value": numbers,
        "valid_shape": valid_shape,
        "coverage_end": end,
        "covers_file_end": end == file_size if end is not None else False,
        "bytes_after_covered_range": file_size - end if end is not None else None,
    }


def walk_signature_fields(fields, file_size: int, prefix: str = "") -> list[dict]:
    found = []
    for ref in fields or []:
        obj = ref.get_object()
        name = str(obj.get("/T", ""))
        full_name = prefix + name
        field_type = str(obj.get("/FT", ""))
        value = obj.get("/V")
        signature = None
        if value:
            try:
                candidate = value.get_object()
                if candidate.get("/Type") == "/Sig" or candidate.get("/ByteRange") is not None:
                    signature = candidate
            except Exception:
                signature = None
        if field_type == "/Sig" or signature is not None:
            record = {
                "field_name": full_name,
                "field_type": field_type,
                "filter": "",
                "subfilter": "",
                "contents_length": 0,
                "byte_range": analyse_byte_range(None, file_size),
            }
            if value:
                try:
                    signature = value.get_object()
                    record["filter"] = str(signature.get("/Filter", ""))
                    record["subfilter"] = str(signature.get("/SubFilter", ""))
                    contents = signature.get("/Contents", b"")
                    record["contents_length"] = len(contents) if contents else 0
                    record["byte_range"] = analyse_byte_range(signature.get("/ByteRange"), file_size)
                except Exception as exc:
                    record["read_error"] = str(exc)
            found.append(record)
        found.extend(walk_signature_fields(obj.get("/Kids"), file_size, full_name + "/"))
    return found


def inspect_pdf(path: Path, text_fingerprint: bool = True) -> dict:
    result = {
        "path": str(path.resolve()),
        "name": path.name,
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else None,
        "sha256": sha256_file(path) if path.exists() else None,
        "readable": False,
        "encrypted": None,
        "pages": None,
        "signature_fields": [],
        "text_characters": None,
        "normalised_text_sha256": None,
        "warnings": [],
    }
    if not path.exists():
        result["warnings"].append("file_missing")
        return result
    if path.suffix.lower() != ".pdf":
        result["warnings"].append("not_pdf")
        return result

    try:
        reader = PdfReader(path)
        result["encrypted"] = reader.is_encrypted
        if reader.is_encrypted:
            result["warnings"].append("encrypted_pdf")
            return result
        result["pages"] = len(reader.pages)
        result["readable"] = True
        root = reader.trailer["/Root"]
        acro = root.get("/AcroForm")
        if acro:
            result["signature_fields"] = walk_signature_fields(
                acro.get_object().get("/Fields"), result["size"]
            )
        if not result["signature_fields"]:
            result["warnings"].append("no_pdf_signature_field")
        else:
            for field in result["signature_fields"]:
                byte_range = field["byte_range"]
                if not byte_range["valid_shape"]:
                    result["warnings"].append("invalid_signature_byte_range")
                elif not byte_range["covers_file_end"]:
                    result["warnings"].append("bytes_after_signature_coverage")

        if text_fingerprint:
            digest = hashlib.sha256()
            total = 0
            for page in reader.pages:
                text = normalise_text(page.extract_text() or "")
                encoded = text.encode("utf-8", errors="replace")
                total += len(text)
                digest.update(encoded)
                digest.update(b"\f")
            result["text_characters"] = total
            result["normalised_text_sha256"] = digest.hexdigest()
            if total == 0:
                result["warnings"].append("no_extractable_text")
    except Exception as exc:
        result["warnings"].append("pdf_read_error")
        result["error"] = str(exc)
    result["warnings"] = sorted(set(result["warnings"]))
    return result


def duplicate_groups(records: list[dict], key: str) -> list[list[str]]:
    grouped = defaultdict(list)
    for record in records:
        value = record.get(key)
        if value:
            grouped[value].append(record["name"])
    return [names for names in grouped.values() if len(names) > 1]


def main() -> None:
    parser = argparse.ArgumentParser(description="检查签章投标PDF包的签名结构、完整覆盖和重复内容")
    parser.add_argument("pdfs", nargs="+", help="一份或多份签章PDF")
    parser.add_argument("--out", help="输出JSON路径")
    parser.add_argument("--no-text-fingerprint", action="store_true", help="跳过全文文本指纹（超大PDF可提速）")
    parser.add_argument("--strict", action="store_true", help="缺签名域、加密、不可读或签名后有追加字节时非零退出")
    args = parser.parse_args()

    records = [inspect_pdf(Path(value), not args.no_text_fingerprint) for value in args.pdfs]
    result = {
        "files": records,
        "exact_duplicate_groups": duplicate_groups(records, "sha256"),
        "normalised_text_duplicate_groups": duplicate_groups(records, "normalised_text_sha256"),
        "boundary": (
            "本结果只验证PDF本地结构、ByteRange覆盖和内容重复；"
            "不验证CA信任链、签章主体真实性、政采云上传/加密/解密或其他投标人环境。"
        ),
    }

    strict_codes = {
        "file_missing",
        "not_pdf",
        "encrypted_pdf",
        "pdf_read_error",
        "no_pdf_signature_field",
        "invalid_signature_byte_range",
        "bytes_after_signature_coverage",
    }
    failed = False
    for record in records:
        signature_count = len(record["signature_fields"])
        print(
            f"{record['name']}: pages={record['pages']} readable={record['readable']} "
            f"signatures={signature_count} warnings={','.join(record['warnings']) or 'none'}"
        )
        for field in record["signature_fields"]:
            byte_range = field["byte_range"]
            print(
                f"  {field['field_name']} {field['subfilter']} "
                f"covers_end={byte_range['covers_file_end']} contents={field['contents_length']}"
            )
        if strict_codes & set(record["warnings"]):
            failed = True

    if result["exact_duplicate_groups"]:
        print("精确重复文件组:", result["exact_duplicate_groups"])
    if result["normalised_text_duplicate_groups"]:
        print("标准化文本重复组:", result["normalised_text_duplicate_groups"])
    print("边界:", result["boundary"])

    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("out=", output)

    if args.strict and failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
