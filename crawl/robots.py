"""Minimal robots.txt parser and matcher.

Rules are grouped by ``User-agent``.  For a request the longest matching
``Allow``/``Disallow`` rule wins; on an exact tie ``Allow`` wins.  ``*``
wildcards and ``$`` end anchors are supported, and an empty ``Disallow``
means "allow everything" and therefore contributes no rule.
"""

from dataclasses import dataclass
import re


def _compile_pattern(pattern):
    anchored_end = pattern.endswith("$")
    if anchored_end:
        pattern = pattern[:-1]
    pieces = [re.escape(part) for part in pattern.split("*")]
    body = ".*".join(pieces)
    return re.compile("^" + body + ("$" if anchored_end else ""))


def _rule_length(pattern):
    # Match specificity is the literal pattern length, excluding the anchor.
    return len(pattern[:-1] if pattern.endswith("$") else pattern)


@dataclass(frozen=True)
class Rule:
    pattern: str
    allow: bool
    regex: object
    length: int

    def matches(self, path):
        return self.regex.match(path) is not None


@dataclass(frozen=True)
class Robots:
    groups: dict
    sitemaps: tuple

    @classmethod
    def parse(cls, text):
        groups = {}
        current_agents = None
        current_agents_closed = False
        sitemaps = []

        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            if ":" not in line:
                continue
            field, value = line.split(":", 1)
            field = field.strip().lower()
            value = value.strip()

            if field == "user-agent":
                agent = value.lower()
                if current_agents is None or current_agents_closed:
                    current_agents = [agent]
                    current_agents_closed = False
                else:
                    current_agents.append(agent)
                groups.setdefault(agent, [])
            elif field in ("allow", "disallow"):
                if current_agents is None or value == "":
                    # Empty Disallow means "allow all"; empty Allow is a no-op.
                    continue
                rule = Rule(
                    pattern=value,
                    allow=(field == "allow"),
                    regex=_compile_pattern(value),
                    length=_rule_length(value),
                )
                for agent in current_agents:
                    groups.setdefault(agent, []).append(rule)
                current_agents_closed = True
            elif field == "sitemap":
                sitemaps.append(value)
            else:
                # A non-agent/non-rule field ends the current group.
                if field not in ("crawl-delay",):
                    current_agents = None

        return cls(groups=groups, sitemaps=tuple(sitemaps))

    def _rules_for(self, user_agent):
        token = (user_agent or "*").lower()
        for agent in token.split(None) or [token]:
            if agent in self.groups:
                return self.groups[agent]
        return self.groups.get("*", [])

    def allowed(self, path, user_agent="*"):
        chosen = None
        for rule in self._rules_for(user_agent):
            if not rule.matches(path):
                continue
            if chosen is None or rule.length > chosen.length:
                chosen = rule
            elif rule.length == chosen.length and rule.allow:
                chosen = rule
        if chosen is None:
            return True
        return chosen.allow
