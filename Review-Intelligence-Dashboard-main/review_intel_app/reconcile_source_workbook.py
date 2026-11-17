"""Read-only, aggregate-only comparison of an Outscraper XLSX and review CSV.

No network access, analyzer imports, source updates or provenance certification.
Only the simple, single-sheet, string/numeric OOXML export layout is supported.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from audit_source_coverage import ROOT, PRIVATE

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
WORKBOOK_FIELDS = {
    "query", "name", "place_id", "google_id", "reviews", "review_id",
    "review_pagination_id", "review_text", "review_rating", "review_timestamp",
    "review_datetime_utc", "owner_answer",
}
CSV_FIELDS = {"date", "rating", "text", "review_id", "owner_replied"}


def normalize_text(value):
    """Only HTML line-break tags and whitespace; no case/word/punctuation edits."""
    return " ".join(re.sub(r"<br\s*/?>", " ", value, flags=re.I).split())


def read_workbook(raw):
    with ZipFile(io.BytesIO(raw)) as z:
        if sum(i.file_size for i in z.infolist()) > 100_000_000:
            raise ValueError("Workbook exceeds audit size limit.")
        book = ET.fromstring(z.read("xl/workbook.xml"))
        sheets = book.findall("s:sheets/s:sheet", NS)
        if len(sheets) != 1:
            raise ValueError("Expected exactly one sheet; inspect extra sheets separately.")
        rel_id = sheets[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rel = next((r for r in rels if r.get("Id") == rel_id), None)
        if rel is None or rel.get("TargetMode") == "External":
            raise ValueError("Missing internal worksheet relationship.")
        target = rel.get("Target", "")
        sheet_path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if ".." in Path(sheet_path).parts or not sheet_path.startswith("xl/worksheets/"):
            raise ValueError("Unsupported worksheet path.")
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = ["".join(t.text or "" for t in si.findall(".//s:t", NS))
                       for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]

        def cell_value(cell):
            if cell.find("s:f", NS) is not None:
                raise ValueError("Formula cells are not accepted as source metadata.")
            kind = cell.get("t")
            if kind == "inlineStr":
                return "".join(t.text or "" for t in cell.findall(".//s:t", NS))
            v = cell.find("s:v", NS)
            value = v.text if v is not None and v.text else ""
            if kind == "s":
                index = int(value)
                if not 0 <= index < len(strings):
                    raise ValueError("Invalid shared string index.")
                return strings[index]
            if kind not in (None, "n", "str"):
                raise ValueError("Unsupported source cell type.")
            return value

        raw_rows = ET.fromstring(z.read(sheet_path)).findall("s:sheetData/s:row", NS)
        if not raw_rows:
            raise ValueError("Empty sheet.")
        headers = {re.sub(r"\d", "", c.get("r", "")): cell_value(c) for c in raw_rows[0]}
        if len(set(headers.values())) != len(headers) or not WORKBOOK_FIELDS <= set(headers.values()):
            raise ValueError("Missing or duplicated workbook columns.")
        rows = []
        for row in raw_rows[1:]:
            result = dict.fromkeys(headers.values(), "")
            for cell in row:
                col = re.sub(r"\d", "", cell.get("r", ""))
                if col not in headers:
                    raise ValueError("Cell outside the source header range.")
                result[headers[col]] = cell_value(cell)
            if any(result.values()):
                rows.append(result)
        properties = ET.fromstring(z.read("docProps/core.xml"))
        dates = {key: properties.findtext("{http://purl.org/dc/terms/}" + key)
                 for key in ("created", "modified")}
        return rows, dates


def compare(rows, csv_rows):
    if not rows or not csv_rows:
        raise ValueError("Empty inputs cannot establish a match.")
    dates = [datetime.strptime(r["review_datetime_utc"], "%m/%d/%Y %H:%M:%S")
             .replace(tzinfo=timezone.utc) for r in rows]
    timestamp_matches = sum(datetime.fromtimestamp(float(r["review_timestamp"]), timezone.utc) == d
                            for r, d in zip(rows, dates))
    selected = [(r, d) for r, d in zip(rows, dates) if r["review_text"].strip()]
    workbook_keys = [(d.date().isoformat(), r["review_rating"], normalize_text(r["review_text"]))
                     for r, d in selected]
    csv_keys = [(r["date"], r["rating"], normalize_text(r["text"])) for r in csv_rows]
    overlap = sum((Counter(workbook_keys) & Counter(csv_keys)).values())
    business = {key: dict(Counter(r.get(key, "") for r in rows))
                for key in ("name", "google_id", "place_id", "reviews", "reviews_per_score")}
    return {
        "workbook_rows": len(rows), "csv_rows": len(csv_rows),
        "workbook_text_rows": len(selected), "workbook_blank_text_rows": len(rows) - len(selected),
        "business_metadata_claims": business,
        "query_distinct_count": len({r["query"] for r in rows}),
        "query_mentions_newest_60_rows": sum(bool(re.search(r"newest\s+60\b", r["query"], re.I)) for r in rows),
        "package_metadata_is_not_authenticated_job_time": True,
        "timestamp_datetime_matches": timestamp_matches,
        "workbook_utc_start": min(dates).isoformat(), "workbook_utc_end": max(dates).isoformat(),
        "timestamps_nonincreasing": all(a >= b for a, b in zip(dates, dates[1:])),
        "csv_text_date_rating_multiset_matches": overlap,
        "csv_text_date_rating_ordered_matches": sum(a == b for a, b in zip(csv_keys, workbook_keys)),
        "complete_text_date_rating_match": Counter(workbook_keys) == Counter(csv_keys),
        "unique_workbook_text_date_rating_tuples": len(set(workbook_keys)),
        "exact_text_ordered_matches": sum(a["text"] == b["review_text"] for a, (b, _) in zip(csv_rows, selected)),
        "whitespace_only_text_ordered_matches": sum(" ".join(a["text"].split()) == " ".join(b["review_text"].split())
                                                     for a, (b, _) in zip(csv_rows, selected)),
        "ordered_owner_reply_presence_matches": sum(a["owner_replied"] == ("yes" if b["owner_answer"].strip() else "no")
                                                     for a, (b, _) in zip(csv_rows, selected)),
        "shared_nonblank_review_ids": len({r["review_id"] for r in rows if r["review_id"]} &
                                          {r["review_id"] for r in csv_rows if r["review_id"]}),
        "workbook_unique_nonblank_review_ids": len({r["review_id"] for r in rows if r["review_id"]}),
        "populated_pagination_markers": sum(bool(r["review_pagination_id"]) for r in rows),
        "pagination_completion_verified": False,
        "text_rows_with_different_eastern_calendar_day": sum(d.date() != d.astimezone(ZoneInfo("America/New_York")).date()
                                                            for _, d in selected),
        "collection_settings_verified": False,
        "independent_authentication": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True)
    args = parser.parse_args()
    # Read and hash bytes before parsing. Never write either input.
    workbook_raw, csv_raw = args.workbook.read_bytes(), args.export.read_bytes()
    rows, properties = read_workbook(workbook_raw)
    reader = csv.DictReader(io.StringIO(csv_raw.decode("utf-8-sig")))
    csv_rows = list(reader)
    if not CSV_FIELDS <= set(reader.fieldnames or []) or any(None in r or None in r.values() for r in csv_rows):
        raise ValueError("Missing columns or malformed CSV.")
    result = compare(rows, csv_rows)
    result.update({
        "method": "Exact date/rating and case-sensitive text after br-tag/whitespace normalization; multiset and ordered comparisons; aggregate-only.",
        "input_sha256": {"workbook": hashlib.sha256(workbook_raw).hexdigest(), "csv": hashlib.sha256(csv_raw).hexdigest()},
        "package_claimed_times": properties,
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    folder = PRIVATE / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_reconciliation")
    folder.mkdir(parents=True, mode=0o700)
    output = folder / "workbook_reconciliation_PRIVATE.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    output.chmod(0o600)
    manifest = folder / "SHA256SUMS.json"
    manifest.write_text(json.dumps({output.name: hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2) + "\n")
    manifest.chmod(0o600)
    print("Private aggregate comparison saved:", folder.relative_to(ROOT))


if __name__ == "__main__":
    main()
