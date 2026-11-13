import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from crawl.cli import run
from crawl.policy import CrawlPolicy, Deduplicator
from crawl.robots import Robots
from crawl.sitemap import iter_sitemap_urls, parse_sitemap
from crawl.urlnorm import host_of, normalize_url, origin_path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_SITE = REPO_ROOT / "demo" / "site"

ROBOTS_TEXT = """User-agent: *
Disallow: /private/
Allow: /private/public/
Disallow: /admin/

User-agent: botA
Disallow:
"""


class RobotsSemanticsTest(unittest.TestCase):
    def setUp(self):
        self.robots = Robots.parse(ROBOTS_TEXT)

    def test_groups_and_longest_match_wins(self):
        # /private/ forbids, but the longer /private/public/ allows.
        self.assertFalse(self.robots.allowed("/private/secret.html", "*"))
        self.assertTrue(
            self.robots.allowed("/private/public/allowed.html", "*")
        )
        self.assertFalse(self.robots.allowed("/admin/dashboard.html", "*"))
        self.assertTrue(self.robots.allowed("/index.html", "*"))

    def test_empty_disallow_allows_everything(self):
        self.assertTrue(self.robots.allowed("/private/secret.html", "botA"))
        self.assertTrue(self.robots.allowed("/admin/dashboard.html", "botA"))

    def test_wildcard_and_end_anchor(self):
        robots = Robots.parse(
            "User-agent: *\n"
            "Disallow: /*.tmp$\n"
            "Allow: /assets/*/logo.png$\n"
        )
        self.assertFalse(robots.allowed("/download/data.tmp", "*"))
        # The end anchor means an extra path segment does not match.
        self.assertTrue(robots.allowed("/download/data.tmp/ok", "*"))
        self.assertTrue(robots.allowed("/assets/v2/logo.png", "*"))
        self.assertTrue(robots.allowed("/assets/v2/logo.png.bak", "*"))
        self.assertFalse(robots.allowed("/assets/v2/logo.png.tmp", "*"))

    def test_equal_length_allow_wins(self):
        robots = Robots.parse(
            "User-agent: *\n"
            "Disallow: /same-rule\n"
            "Allow: /same-rule\n"
        )
        self.assertTrue(robots.allowed("/same-rule", "*"))

    def test_specific_user_agent_group_wins_over_wildcard(self):
        robots = Robots.parse(
            "User-agent: *\nDisallow: /x/\n\n"
            "User-agent: special\nDisallow: /y/\n"
        )
        self.assertTrue(robots.allowed("/x/a", "special"))
        self.assertFalse(robots.allowed("/y/a", "special"))
        self.assertFalse(robots.allowed("/x/a", "other"))

    def test_new_user_agent_after_rule_starts_a_fresh_group(self):
        robots = Robots.parse(
            "User-agent: first\nDisallow: /a/\n"
            "User-agent: second\nDisallow: /b/\n"
        )
        self.assertFalse(robots.allowed("/a/page", "first"))
        self.assertTrue(robots.allowed("/b/page", "first"))
        self.assertTrue(robots.allowed("/a/page", "second"))
        self.assertFalse(robots.allowed("/b/page", "second"))

    def test_policy_maps_file_urls_to_site_relative_paths(self):
        policy = CrawlPolicy(robots=self.robots, site_root=DEMO_SITE)
        secret = (DEMO_SITE / "private" / "secret.html").resolve().as_uri()
        allowed = (
            DEMO_SITE / "private" / "public" / "allowed.html"
        ).resolve().as_uri()
        self.assertFalse(policy.is_allowed(secret))
        self.assertTrue(policy.is_allowed(allowed))
        self.assertEqual(
            origin_path(secret, DEMO_SITE), "/private/secret.html"
        )


class UrlNormalizationTest(unittest.TestCase):
    def test_fragment_host_case_and_relative_resolution(self):
        self.assertEqual(
            normalize_url("/Index.html#part", "file:///site/sitemap.xml"),
            "file:///site/Index.html",
        )
        self.assertEqual(
            normalize_url("HTTP://Example.COM/a/../b?x=1#f"),
            "http://example.com/b?x=1",
        )
        self.assertEqual(
            normalize_url("http://Example.COM"), "http://example.com/"
        )
        self.assertEqual(
            normalize_url("child.html", "http://Ex.COM/n/"),
            "http://ex.com/n/child.html",
        )
        self.assertEqual(
            normalize_url("../b.html", "http://Ex.COM/n/a/"),
            "http://ex.com/n/b.html",
        )
        self.assertEqual(
            host_of("http://Example.COM:8080/a"), "example.com:8080"
        )

    def test_deduplicator_counts_only_later_copies(self):
        dedupe = Deduplicator()
        self.assertFalse(dedupe.is_duplicate("http://a/"))
        self.assertFalse(dedupe.is_duplicate("http://b/"))
        self.assertTrue(dedupe.is_duplicate("http://a/"))


class SitemapTest(unittest.TestCase):
    def test_parse_index_and_urlset_with_lastmod(self):
        index = (
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<sitemap><loc>/a.xml</loc><lastmod>2026-01-01</lastmod></sitemap>"
            "</sitemapindex>"
        )
        kind, entries = parse_sitemap(index, "file:///site/sitemap.xml")
        self.assertEqual(kind, "index")
        self.assertEqual(entries[0].loc, "file:///site/a.xml")
        self.assertEqual(entries[0].lastmod, "2026-01-01")

        urlset = (
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<url><loc>page.html</loc><lastmod>2026-02-01</lastmod></url>"
            "</urlset>"
        )
        kind, entries = parse_sitemap(urlset, "file:///site/sm.xml")
        self.assertEqual(kind, "urlset")
        self.assertEqual(entries[0].loc, "file:///site/page.html")
        self.assertEqual(entries[0].lastmod, "2026-02-01")

    def test_self_reference_stops_and_depth_is_limited_to_two_expansions(self):
        # level 0 index -> level 1 index -> level 2 index must not expand.
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "root.xml").write_text(
                "<sitemapindex>"
                "<sitemap><loc>root.xml</loc></sitemap>"
                "<sitemap><loc>level1.xml</loc></sitemap>"
                "</sitemapindex>",
                encoding="utf-8",
            )
            (site / "level1.xml").write_text(
                "<sitemapindex>"
                "<sitemap><loc>level2.xml</loc></sitemap>"
                "</sitemapindex>",
                encoding="utf-8",
            )
            (site / "level2.xml").write_text(
                "<sitemapindex>"
                "<sitemap><loc>level3.xml</loc></sitemap>"
                "</sitemapindex>",
                encoding="utf-8",
            )
            (site / "level3.xml").write_text(
                "<urlset><url><loc>never.html</loc></url></urlset>",
                encoding="utf-8",
            )

            def load_text(url):
                return Path(url[len("file://"):]).read_text(encoding="utf-8")

            locs = [
                entry.loc
                for entry in iter_sitemap_urls((site / "root.xml").as_uri(),
                                               load_text)
            ]
            self.assertEqual(locs, [])

    def test_urlset_beyond_depth_would_yield_at_allowed_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "root.xml").write_text(
                "<sitemapindex><sitemap><loc>level1.xml</loc></sitemap>"
                "</sitemapindex>",
                encoding="utf-8",
            )
            (site / "level1.xml").write_text(
                "<sitemapindex><sitemap><loc>level2.xml</loc></sitemap>"
                "</sitemapindex>",
                encoding="utf-8",
            )
            (site / "level2.xml").write_text(
                "<urlset><url><loc>page.html</loc></url></urlset>",
                encoding="utf-8",
            )

            def load_text(url):
                return Path(url[len("file://"):]).read_text(encoding="utf-8")

            locs = [
                entry.loc
                for entry in iter_sitemap_urls((site / "root.xml").as_uri(),
                                               load_text)
            ]
            self.assertEqual(locs, [(site / "page.html").resolve().as_uri()])


class PolitenessTest(unittest.TestCase):
    def test_same_host_wait_and_independent_hosts(self):
        current = [100.0]
        sleeps = []
        policy = CrawlPolicy(
            delay_seconds=2.0,
            clock=lambda: current[0],
            sleeper=lambda seconds: sleeps.append(seconds),
        )

        policy.throttle("http://a.test/one")
        self.assertEqual(sleeps, [])
        current[0] = 101.0
        policy.throttle("http://a.test/two")
        self.assertEqual(sleeps, [1.0])

        # A different host has its own schedule and does not wait.
        policy.throttle("http://b.test/one")
        self.assertEqual(sleeps, [1.0])

    def test_zero_delay_never_sleeps(self):
        sleeps = []
        policy = CrawlPolicy(delay_seconds=0.0,
                             sleeper=lambda seconds: sleeps.append(seconds))
        policy.throttle("file:///tmp/a")
        policy.throttle("file:///tmp/b")
        self.assertEqual(sleeps, [])


class CrawlCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.site = Path(self.tmp.name) / "site"
        shutil.copytree(DEMO_SITE, self.site)
        self.report_path = Path(self.tmp.name) / "out" / "report.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _report(self):
        report = run(self.site, self.report_path, delay_seconds=0.0)
        on_disk = json.loads(self.report_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, report)
        return report

    def test_demo_fixture_satisfies_all_seven_judgement_rules(self):
        report = self._report()
        summary = report["summary"]

        # Rule 1/2: six sitemap entries, five unique URLs, exactly 3 crawled.
        crawled = report["crawled"]
        crawled_urls = {item["url"] for item in crawled}
        self.assertEqual(summary["candidate_urls"], 6)
        self.assertEqual(len(crawled), 3)

        longest_match = (
            self.site / "private" / "public" / "allowed.html"
        ).resolve().as_uri()
        home = (self.site / "index.html").resolve().as_uri()
        about = (self.site / "about.html").resolve().as_uri()
        self.assertEqual(crawled_urls, {home, about, longest_match})
        # Rule 5: this page is only reachable because the longer Allow wins.
        self.assertIn(longest_match, crawled_urls)

        # Rule 3: the two forbidden URLs are counted, never crawled.
        blocked = {
            (self.site / "private" / "secret.html").resolve().as_uri(),
            (self.site / "admin" / "dashboard.html").resolve().as_uri(),
        }
        self.assertEqual(set(report["skipped_by_robots"]), blocked)
        self.assertTrue(blocked.isdisjoint(crawled_urls))
        self.assertEqual(summary["skipped_by_robots"], 2)

        # Rule 4: fragment normalization makes the second home a duplicate.
        self.assertEqual(report["skipped_duplicate"], [home])
        self.assertEqual(summary["skipped_duplicate"], 1)

        # Rule 7: report sections and crawled record shape.
        self.assertEqual(
            set(report),
            {
                "crawled",
                "skipped_by_robots",
                "skipped_duplicate",
                "not_found",
                "summary",
            },
        )
        for item in crawled:
            self.assertEqual(
                set(item), {"url", "status", "bytes", "title"}
            )
            self.assertEqual(item["status"], 200)
            self.assertGreater(item["bytes"], 0)
            self.assertTrue(item["title"])

    def test_missing_file_is_reported_as_not_found(self):
        sitemap = (
            "<urlset><url><loc>/missing.html</loc></url></urlset>"
        )
        (self.site / "missing-sitemap.xml").write_text(
            sitemap, encoding="utf-8"
        )
        report = run(
            self.site,
            self.report_path,
            delay_seconds=0.0,
            sitemap_name="missing-sitemap.xml",
        )
        missing = (self.site / "missing.html").resolve().as_uri()
        self.assertEqual(report["not_found"], [missing])
        self.assertEqual(report["crawled"], [])
        self.assertEqual(report["summary"]["not_found"], 1)

    def test_command_line_entry_prints_one_line_summary(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "crawl.cli",
                "--site",
                str(self.site),
                "--out",
                str(self.report_path),
                "--delay",
                "0",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        numbers = [int(value) for value in re.findall(r":\s*(\d+)", lines[0])]
        self.assertEqual(numbers, [6, 3, 2, 1])
        report = json.loads(self.report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["candidate_urls"], 6)


if __name__ == "__main__":
    unittest.main()
