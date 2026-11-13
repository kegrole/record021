"""Command line entry point for the sitemap-only crawler."""

import argparse
from pathlib import Path

from .fetch import DefaultFetcher
from .policy import CrawlPolicy, Deduplicator
from .report import build_report, write_report
from .robots import Robots
from .sitemap import iter_sitemap_urls
from .urlnorm import normalize_url


def _site_file_url(site_dir, relative):
    return Path(site_dir, relative).resolve().as_uri()


def run(site_dir, output_path, user_agent="DemoBot/1.0", delay_seconds=0.5,
        sitemap_name=None):
    site_dir = Path(site_dir)
    fetcher = DefaultFetcher(user_agent=user_agent)

    robots_path = site_dir / "robots.txt"
    if robots_path.is_file():
        robots = Robots.parse(robots_path.read_text(encoding="utf-8"))
    else:
        robots = Robots(groups={}, sitemaps=())

    if sitemap_name:
        entry_sitemap = _site_file_url(site_dir, sitemap_name)
    elif robots.sitemaps:
        entry_sitemap = normalize_url(
            robots.sitemaps[0], _site_file_url(site_dir, "robots.txt")
        )
    else:
        entry_sitemap = _site_file_url(site_dir, "sitemap.xml")

    policy = CrawlPolicy(
        robots=robots,
        user_agent=user_agent,
        delay_seconds=delay_seconds,
        site_root=site_dir,
    )
    dedupe = Deduplicator()

    crawled = []
    skipped_by_robots = []
    skipped_duplicate = []
    not_found = []
    candidates = 0

    for entry in iter_sitemap_urls(entry_sitemap, fetcher.load_text):
        candidates += 1
        url = entry.loc
        if dedupe.is_duplicate(url):
            skipped_duplicate.append(url)
            continue
        if not policy.is_allowed(url):
            skipped_by_robots.append(url)
            continue

        policy.throttle(url)
        result = fetcher.fetch(url)
        if result.missing:
            not_found.append(url)
        else:
            crawled.append(result)

    report = build_report(
        crawled=crawled,
        skipped_by_robots=skipped_by_robots,
        skipped_duplicate=skipped_duplicate,
        not_found=not_found,
        candidates=candidates,
    )
    write_report(report, output_path)

    summary = report["summary"]
    print(
        "候选 URL 数: {candidate_urls}，采集数: {crawled}，"
        "robots 拦截数: {skipped_by_robots}，去重数: {skipped_duplicate}".format(
            **summary
        )
    )
    return report


def build_parser():
    parser = argparse.ArgumentParser(
        description="Crawl only the URLs listed in a sitemap, obeying robots.txt."
    )
    parser.add_argument("--site", required=True, help="site directory")
    parser.add_argument("--out", required=True, help="JSON report output path")
    parser.add_argument("--user-agent", default="DemoBot/1.0")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="minimum seconds between requests to one host")
    parser.add_argument("--sitemap", default=None,
                        help="sitemap file name inside the site directory")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    run(
        site_dir=args.site,
        output_path=args.out,
        user_agent=args.user_agent,
        delay_seconds=args.delay,
        sitemap_name=args.sitemap,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
