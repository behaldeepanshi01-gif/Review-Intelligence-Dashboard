"""Collect official-site testimonials only. No Google requests or app imports.

Run from this directory: python collect_website_reviews.py
Only aggregate counts are printed. Outputs must never enter source bundles.
"""
import csv
import hashlib
import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

BASE = "https://mumbaicentralva.com/"
AGENT = "ReviewIntelligenceWebsiteCheck/1.0"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"}


class Node:
    def __init__(self, tag="", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self):
        return "".join(c.text() if isinstance(c, Node) else c for c in self.children)

    def has_class(self, name):
        return name in self.attrs.get("class", "").split()


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def clean(text):
    return " ".join(text.split())


def extract(html, url, retrieved):
    """Preserve published wording, normalizing only HTML whitespace.

    Identity headings are never exported. Include them only inside a one-way
    record fingerprint so different reviewers with identical wording stay distinct.
    """
    root = Document(html).root
    records = []
    for section in root.walk():
        if section.attrs.get("id") != "reviews_v2":
            continue
        for item in section.walk():
            if not item.has_class("item"):
                continue
            nodes = list(item.walk())
            quotes = [n for n in nodes if n.tag == "blockquote"]
            if not quotes:
                continue
            text = clean(" ".join(n.text() for n in quotes))
            attribution = clean(" ".join(n.text() for n in nodes
                                        if n.has_class("review-by")))
            stars = sum(n.has_class("fa-star") for n in nodes)
            dates = [n.attrs.get("datetime", "") for n in nodes if n.tag == "time"]
            rating = str(stars) if 1 <= stars <= 5 else ""
            date = dates[0] if dates else ""
            identity_heading = clean(" ".join(n.text() for n in nodes
                                             if n.has_class("reviewer")))
            identity = json.dumps([text, rating, attribution, date, identity_heading],
                                  ensure_ascii=False)
            records.append({
                "review_id": "MC-WEB-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
                "location": "Mumbai Central, Falls Church",
                "date": date, "rating": rating, "text": text,
                "source_url": url, "source_attribution": attribution,
                "source_type": "official_website_testimonial",
                "retrieved_at_utc": retrieved,
            })
    links = [urljoin(url, n.attrs["href"]) for n in root.walk()
             if n.tag == "a" and n.attrs.get("href")]
    return records, links


def official_url(url):
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or parts.hostname != "mumbaicentralva.com":
        return None
    # Query strings on promotional links do not change the underlying page.
    return urljoin(BASE, parts.path or "/")


def fetch(url):
    # Refuse cross-domain redirects before requesting the destination.
    from urllib.request import HTTPRedirectHandler, build_opener

    class OfficialRedirects(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not official_url(newurl):
                raise ValueError("External redirect refused")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    with build_opener(OfficialRedirects()).open(
            Request(url, headers={"User-Agent": AGENT}), timeout=30) as response:
        body = response.read(3_000_001)
        if len(body) > 3_000_000:
            raise ValueError("Page exceeds collection size limit")
        return body, response.status, response.url


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = Path(__file__).resolve().parent / "data/private_website_reviews" / stamp
    out.mkdir(parents=True, exist_ok=False)
    retrieved = datetime.now(timezone.utc).isoformat()
    robots_body, _, _ = fetch(BASE + "robots.txt")
    robots = RobotFileParser()
    robots.parse(robots_body.decode().splitlines())
    delay = max(1, robots.crawl_delay(AGENT) or 0)
    pages = [{"url": BASE + "robots.txt", "status": 200,
              "sha256": hashlib.sha256(robots_body).hexdigest()}]
    queue = [BASE]
    for sitemap in robots.site_maps() or [BASE + "sitemap.xml"]:
        if not official_url(sitemap) or not robots.can_fetch(AGENT, sitemap):
            continue
        time.sleep(delay)
        body, status, final = fetch(sitemap)
        pages.append({"url": sitemap, "status": status,
                      "sha256": hashlib.sha256(body).hexdigest()})
        root = ET.fromstring(body)
        queue.extend(n.text for n in root.iter() if n.tag.endswith("}loc") and n.text)
    visited, unique, occurrences = set(), {}, 0
    while queue and len(visited) < 40:
        url = official_url(queue.pop(0))
        if not url or url in visited:
            continue
        visited.add(url)
        if not robots.can_fetch(AGENT, url):
            pages.append({"url": url, "status": "robots_disallowed"})
            continue
        time.sleep(delay)
        try:
            body, status, final = fetch(url)
            html = body.decode("utf-8")
            rows, links = extract(html, final, retrieved)
            nodes = list(Document(html).root.walk())
            quote_blocks = sum(n.tag == "blockquote" for n in nodes)
            review_blocks = sum(n.has_class("review-text") for n in nodes)
            # Fail visibly if other testimonial markup needs inspection.
            import re
            structured_reviews = len(re.findall(r'"@type"\s*:\s*"Review"', html))
            pages.append({"url": url, "final_url": final, "status": status,
                          "review_occurrences": len(rows),
                          "blockquote_count": quote_blocks,
                          "review_text_blocks": review_blocks,
                          "structured_review_count": structured_reviews,
                          "sha256": hashlib.sha256(body).hexdigest(),
                          "pagination_candidate_links": [
                              link for link in links if official_url(link) and
                              any(word in link.lower() for word in
                                  ("review", "testimonial", "page="))]})
            if quote_blocks != len(rows) or review_blocks != len(rows) or structured_reviews:
                raise ValueError("Additional review markup needs private inspection")
            occurrences += len(rows)
            for row in rows:
                unique.setdefault(row["review_id"], row)
            queue.extend(link for link in links if official_url(link))
        except Exception as exc:
            pages.append({"url": url, "status": "failed",
                          "error_type": type(exc).__name__})
    rows = list(unique.values())
    if not rows:
        raise RuntimeError("No testimonials extracted. Inspect site structure privately.")
    csv_path = out / "website_testimonials_PRIVATE.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "retrieved_at_utc": retrieved, "website": BASE,
        "unique_testimonials": len(rows), "occurrences": occurrences,
        "duplicates_removed": occurrences - len(rows),
        "missing_dates": sum(not r["date"] for r in rows),
        "pages_checked": pages, "crawl_limit_reached": bool(queue),
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "limits": [
            "Selected website testimonials attributed to Google, not independently collected Google reviews.",
            "No evidence this is the complete Google review history.",
            "Positive selection bias: these are website-selected testimonials.",
            "No displayed review dates; retrieval times are not publication dates.",
            "Not suitable for early warnings, weekly trends, representative complaint rates or tagging accuracy.",
            "Current dashboard loader drops undated rows. Do not import this as a dated dataset.",
            "No third-party links, private endpoints or browser scripts were fetched.",
            "Static HTML and publicly linked official pages checked; undisclosed dynamic content may exist.",
            "Keep all real review wording private, including downloads. Exclude from demos and source ZIPs.",
        ],
    }
    (out / "collection_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"private_output_directory": str(out),
                      "unique_testimonials": len(rows),
                      "occurrences": occurrences, "pages_checked": len(pages),
                      "missing_dates": summary["missing_dates"]}))


if __name__ == "__main__":
    main()
