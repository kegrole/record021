"""Crawl policy: robots enforcement, dedupe state and per-host politeness."""

import time

from .robots import Robots
from .urlnorm import host_of, origin_path


class CrawlPolicy:
    def __init__(self, robots=None, user_agent="DemoBot/1.0", delay_seconds=0.5,
                 site_root=None, clock=time.monotonic, sleeper=time.sleep):
        self.robots = robots or Robots(groups={}, sitemaps=())
        self.user_agent = user_agent
        self.delay_seconds = max(0.0, float(delay_seconds))
        self.site_root = site_root
        self._clock = clock
        self._sleeper = sleeper
        self._last_request = {}

    def is_allowed(self, url):
        path = origin_path(url, self.site_root)
        return self.robots.allowed(path, self.user_agent)

    def wait_time_for(self, url):
        if self.delay_seconds == 0.0:
            return 0.0
        host = host_of(url)
        last = self._last_request.get(host)
        if last is None:
            return 0.0
        return max(0.0, self.delay_seconds - (self._clock() - last))

    def throttle(self, url):
        wait_seconds = self.wait_time_for(url)
        if wait_seconds > 0.0:
            self._sleeper(wait_seconds)
        self._last_request[host_of(url)] = self._clock()


class Deduplicator:
    """Track normalized URLs; the first occurrence wins."""

    def __init__(self):
        self._seen = set()

    def is_duplicate(self, url):
        if url in self._seen:
            return True
        self._seen.add(url)
        return False
