import importlib.util
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, ByteStringObject, DictionaryObject, NameObject, NumberObject


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inspect_signed_bid_package.py"
SPEC = importlib.util.spec_from_file_location("inspect_signed_bid_package", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SignedPackageTests(unittest.TestCase):
    def test_byte_range_covering_file_end(self):
        result = MODULE.analyse_byte_range([0, 100, 200, 50], 250)
        self.assertTrue(result["valid_shape"])
        self.assertTrue(result["covers_file_end"])
        self.assertEqual(result["bytes_after_covered_range"], 0)

    def test_byte_range_detects_appended_bytes(self):
        result = MODULE.analyse_byte_range([0, 100, 200, 50], 260)
        self.assertFalse(result["covers_file_end"])
        self.assertEqual(result["bytes_after_covered_range"], 10)

    def test_unsigned_pdf_is_reported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "unsigned.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            with path.open("wb") as handle:
                writer.write(handle)
            record = MODULE.inspect_pdf(path)
            self.assertTrue(record["readable"])
            self.assertIn("no_pdf_signature_field", record["warnings"])

    def test_walk_signature_fields_detects_only_signature_values(self):
        signature = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Sig"),
                NameObject("/SubFilter"): NameObject("/adbe.pkcs7.detached"),
                NameObject("/ByteRange"): ArrayObject(
                    [NumberObject(0), NumberObject(20), NumberObject(30), NumberObject(70)]
                ),
                NameObject("/Contents"): ByteStringObject(b"test-signature"),
            }
        )
        signature_field = DictionaryObject(
            {
                NameObject("/FT"): NameObject("/Sig"),
                NameObject("/V"): signature,
            }
        )
        text_field = DictionaryObject(
            {
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/V"): ByteStringObject(b"ordinary-value"),
            }
        )

        found = MODULE.walk_signature_fields([signature_field, text_field], 100)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["field_type"], "/Sig")
        self.assertTrue(found[0]["byte_range"]["covers_file_end"])


if __name__ == "__main__":
    unittest.main()
