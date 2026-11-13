"""JSON report construction and serialization."""

import json
from pathlib import Path


def build_report(crawled, skipped_by_robots, skipped_duplicate, not_found,
                 candidates):
    crawled_records = [
        {
            "url": result.url,
            "status": result.status,
            "bytes": result.bytes,
            "title": result.title,
        }
        for result in crawled
    ]
    summary = {
        "candidate_urls": candidates,
        "crawled": len(crawled_records),
        "skipped_by_robots": len(skipped_by_robots),
        "skipped_duplicate": len(skipped_duplicate),
        "not_found": len(not_found),
    }
    return {
        "crawled": crawled_records,
        "skipped_by_robots": list(skipped_by_robots),
        "skipped_duplicate": list(skipped_duplicate),
        "not_found": list(not_found),
        "summary": summary,
    }


def write_report(report, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
