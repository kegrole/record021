"""Standard-library fetch layer for local files and HTTP(S)."""

from dataclasses import dataclass
import html
import re
from pathlib import Path
from urllib.request import Request, urlopen

TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    bytes: int
    title: str
    missing: bool = False


def extract_title(body):
    match = TITLE_RE.search(body)
    if not match:
        return ""
    return html.unescape(match.group(1).decode("utf-8", "replace").strip())


class DefaultFetcher:
    """Fetch documents via ``file:`` (the demo site) or HTTP(S)."""

    def __init__(self, user_agent="DemoBot/1.0"):
        self.user_agent = user_agent

    def load_text(self, url):
        if url.startswith("file:"):
            return Path(_file_path(url)).read_text(encoding="utf-8")
        request = Request(url, headers={"User-Agent": self.user_agent})
        with urlopen(request, timeout=20) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, "replace")

    def fetch(self, url):
        try:
            if url.startswith("file:"):
                path = Path(_file_path(url))
                if not path.is_file():
                    return FetchResult(url=url, status=404, bytes=0,
                                       title="", missing=True)
                body = path.read_bytes()
                return self._package(url, 200, body)

            request = Request(url, headers={"User-Agent": self.user_agent})
            with urlopen(request, timeout=20) as response:
                body = response.read()
                return self._package(url, response.status, body)
        except Exception as exc:  # network errors are reported, not fatal
            status = getattr(exc, "code", None) or 0
            return FetchResult(url=url, status=int(status or 0), bytes=0,
                               title="", missing=True)

    @staticmethod
    def _package(url, status, body):
        return FetchResult(
            url=url,
            status=status,
            bytes=len(body),
            title=extract_title(body),
            missing=(status == 404),
        )


def _file_path(url):
    from urllib.parse import urlsplit

    return urlsplit(url).path
