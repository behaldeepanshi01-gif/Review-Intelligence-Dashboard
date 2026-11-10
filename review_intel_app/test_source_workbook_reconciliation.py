"""Synthetic-only regression checks for the private workbook audit."""
import io
import json
import unittest
from zipfile import ZipFile
from xml.sax.saxutils import escape

from reconcile_source_workbook import WORKBOOK_FIELDS, compare, normalize_text, read_workbook


def source(text="Good<br> food", stamp="01/02/2026 02:00:00", seconds="1767319200", rating="5", rid="provider-id"):
    result = dict.fromkeys(WORKBOOK_FIELDS, "")
    result.update(review_text=text, review_datetime_utc=stamp, review_timestamp=seconds,
                  review_rating=rating, review_id=rid, name="Fictional Restaurant",
                  place_id="fictional-place", google_id="fictional-google", reviews="10",
                  query="newest 60", review_pagination_id="private-marker")
    return result


def exported(text="Good food", day="2026-01-02", rating="5"):
    return {"text": text, "date": day, "rating": rating, "review_id": "local-id", "owner_replied": "no"}


def workbook_bytes(formula=False, extra_sheet=False):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    fields = sorted(WORKBOOK_FIELDS)
    def col(i):
        return chr(65 + i)
    headers = "".join(f'<c r="{col(i)}1" t="inlineStr"><is><t>{escape(k)}</t></is></c>' for i, k in enumerate(fields))
    cells = "".join(f'<c r="{col(i)}2" t="inlineStr"><is><t>{escape(source()[k])}</t></is></c>' for i, k in enumerate(fields))
    if formula:
        cells = cells.replace('<is>', '<f>1+1</f><is>', 1)
    raw = io.BytesIO()
    with ZipFile(raw, "w") as z:
        extra = '<sheet name="extra" sheetId="2" r:id="rId2"/>' if extra_sheet else ''
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="test" sheetId="1" r:id="rId1"/>{extra}</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{ns}"><sheetData><row>{headers}</row><row>{cells}</row></sheetData></worksheet>')
        z.writestr('docProps/core.xml', '<root xmlns:d="http://purl.org/dc/terms/"><d:created>2026-01-03T00:00:00Z</d:created></root>')
    return raw.getvalue()


class WorkbookReconciliationTests(unittest.TestCase):
    def test_text_only_derivation_without_id_authentication(self):
        result = compare([source(), source(text="", rid="blank-id")], [exported()])
        self.assertEqual(result['workbook_blank_text_rows'], 1)
        self.assertTrue(result['complete_text_date_rating_match'])
        self.assertEqual(result['shared_nonblank_review_ids'], 0)
        self.assertFalse(result['independent_authentication'])
        self.assertFalse(result['pagination_completion_verified'])
        self.assertNotIn('private-marker', json.dumps(result))
        self.assertNotIn('Good', json.dumps(result))

    def test_word_and_rating_differences_do_not_match(self):
        self.assertFalse(compare([source()], [exported(text='Bad food')])['complete_text_date_rating_match'])
        self.assertFalse(compare([source()], [exported(rating='1')])['complete_text_date_rating_match'])
        self.assertNotEqual(normalize_text('GOOD food'), normalize_text('Good food'))

    def test_duplicate_multiplicity_not_set_equality(self):
        r = compare([source(), source(rid='other')], [exported()])
        self.assertEqual(r['csv_text_date_rating_multiset_matches'], 1)
        self.assertFalse(r['complete_text_date_rating_match'])

    def test_order_is_separate_from_membership(self):
        r = compare([source(), source(text='Other', rid='other')], [exported(text='Other'), exported()])
        self.assertTrue(r['complete_text_date_rating_match'])
        self.assertEqual(r['csv_text_date_rating_ordered_matches'], 0)

    def test_utc_dates_not_silently_localized(self):
        r = compare([source()], [exported()])
        self.assertEqual(r['timestamp_datetime_matches'], 1)
        self.assertEqual(r['text_rows_with_different_eastern_calendar_day'], 1)
        self.assertFalse(compare([source()], [exported(day='2026-01-01')])['complete_text_date_rating_match'])

    def test_invalid_or_empty_dates_fail(self):
        with self.assertRaises(ValueError):
            compare([source(stamp='ambiguous')], [exported()])
        with self.assertRaises(ValueError):
            compare([], [])

    def test_inline_string_reader_and_properties(self):
        rows, props = read_workbook(workbook_bytes())
        self.assertEqual(rows, [source()])
        self.assertEqual(props['created'], '2026-01-03T00:00:00Z')

    def test_formulas_and_extra_sheets_fail_closed(self):
        for options in ({'formula': True}, {'extra_sheet': True}):
            with self.assertRaises(ValueError):
                read_workbook(workbook_bytes(**options))


if __name__ == '__main__':
    unittest.main()
