"""URL normalization helpers shared by sitemap parsing and crawling."""

import posixpath
from urllib.parse import urljoin, urlsplit, urlunsplit


def normalize_url(url, base=None):
    """Resolve *url* against *base* and normalize it.

    Fragments are dropped, schemes and hosts are lower-cased, relative
    references are resolved, and empty HTTP(S) paths become ``/``.
    """
    if base is not None:
        if (
            base.startswith("file:")
            and url.startswith("/")
            and not url.startswith("//")
        ):
            # A root-relative reference inside the local site directory is
            # relative to that directory, not the filesystem root.
            base_parts = urlsplit(base)
            site_root = base_parts.path.rsplit("/", 1)[0]
            url = "file://" + site_root + url
        else:
            url = urljoin(base, url)

    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    hostname = parts.hostname
    if hostname is None:
        host = ""
    else:
        host = hostname.lower()
        if parts.port is not None:
            host = f"{host}:{parts.port}"
    if parts.username is not None:
        userinfo = parts.username
        if parts.password is not None:
            userinfo = f"{userinfo}:{parts.password}"
        host = f"{userinfo}@{host}"
    path = parts.path
    if scheme in ("http", "https") and not path:
        path = "/"
    normalized_path = _normalize_dot_segments(path)
    return urlunsplit((scheme, host, normalized_path, parts.query, ""))


def _normalize_dot_segments(path):
    if not path:
        return path
    normalized = posixpath.normpath(path)
    if path.startswith("/"):
        return normalized
    return normalized.lstrip("/")


def host_of(url):
    """Return a stable host key (with explicit port) for politeness waits."""
    parts = urlsplit(url)
    hostname = parts.hostname or ""
    hostname = hostname.lower()
    if parts.port is not None:
        return f"{hostname}:{parts.port}"
    return hostname


def origin_path(url, site_root=None):
    """Return the path used for robots matching.

    HTTP(S) URLs use their own path and query.  ``file:`` URLs that live
    inside *site_root* are mapped to document-root-relative paths so the
    same robots rules work against the local site directory.
    """
    parts = urlsplit(url)
    if parts.scheme == "file" and site_root is not None:
        from pathlib import Path

        root = Path(site_root).resolve()
        document = Path(parts.path)
        try:
            relative = document.resolve().relative_to(root)
        except ValueError:
            relative = Path(parts.path.lstrip("/"))
        path = "/" + relative.as_posix()
        if not path.endswith("/") and document.is_dir():
            path += "/"
    else:
        path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return path
