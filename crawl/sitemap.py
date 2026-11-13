"""sitemapindex / urlset parsing with bounded index expansion."""

from dataclasses import dataclass
from xml.etree import ElementTree

from .urlnorm import normalize_url

# The entry sitemap is expansion 0; nested sitemapindex documents may be
# expanded through this many additional levels, then expansion stops.
MAX_SITEMAP_EXPANSIONS = 2


@dataclass(frozen=True)
class UrlEntry:
    loc: str
    lastmod: str = ""


def _local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def parse_sitemap(text, base_url):
    """Parse one sitemap document.

    Returns ``(kind, entries)`` where *kind* is ``"index"`` or ``"urlset"``
    and *entries* are normalized :class:`UrlEntry` objects.
    """
    root = ElementTree.fromstring(text)
    root_name = _local_name(root.tag)
    entries = []

    if root_name == "sitemapindex":
        for node in root:
            if _local_name(node.tag) != "sitemap":
                continue
            loc = ""
            lastmod = ""
            for child in node:
                name = _local_name(child.tag)
                if name == "loc" and child.text:
                    loc = normalize_url(child.text.strip(), base_url)
                elif name == "lastmod" and child.text:
                    lastmod = child.text.strip()
            if loc:
                entries.append(UrlEntry(loc=loc, lastmod=lastmod))
        return "index", tuple(entries)

    if root_name == "urlset":
        for node in root:
            if _local_name(node.tag) != "url":
                continue
            loc = ""
            lastmod = ""
            for child in node:
                name = _local_name(child.tag)
                if name == "loc" and child.text:
                    loc = normalize_url(child.text.strip(), base_url)
                elif name == "lastmod" and child.text:
                    lastmod = child.text.strip()
            if loc:
                entries.append(UrlEntry(loc=loc, lastmod=lastmod))
        return "urlset", tuple(entries)

    raise ValueError(f"unsupported sitemap root element: {root.tag}")


def iter_sitemap_urls(entry_sitemap_url, load_text):
    """Yield every urlset :class:`UrlEntry` reachable from *entry_sitemap_url*.

    *load_text* receives a sitemap URL and returns its XML text.  Expansion
    stops after :data:`MAX_SITEMAP_EXPANSIONS` nested-index levels, and
    already-visited sitemap documents are skipped (self-references included).
    """
    visited = set()
    pending = [(entry_sitemap_url, 0)]

    while pending:
        sitemap_url, depth = pending.pop(0)
        if sitemap_url in visited:
            continue
        visited.add(sitemap_url)

        kind, entries = parse_sitemap(load_text(sitemap_url), sitemap_url)
        if kind == "urlset":
            for entry in entries:
                yield entry
            continue

        # sitemapindex: stop expanding once the depth budget is exhausted.
        if depth >= MAX_SITEMAP_EXPANSIONS:
            continue
        for entry in entries:
            if entry.loc not in visited:
                pending.append((entry.loc, depth + 1))
