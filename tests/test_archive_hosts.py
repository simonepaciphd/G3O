"""Tests for the versioned archive-host list (PI ruling A2.1 a; v2 rulings 3 b / 4 b, 2026-11-11).

The expected hosts are restated here from the ruling text, not read from the module,
so an edit to the list without a new version fails the test.
"""

from __future__ import annotations

import pytest

from g3o.common import archive_hosts as ah
from g3o.common import source_fields as sf

RULED_HOSTS = {
    "web.archive.org", "wayback.archive.org",
    "archive.ph", "archive.is", "archive.today", "archive.li", "archive.md", "archive.vn",
    "archive.fo",  # ruling 4 b
    "webcache.googleusercontent.com",
}
RULED_PATH_PREFIXES = {"archive.org": ("/details/",)}  # ruling 4 b


def test_list_is_the_ruled_list_with_its_version_and_hash():
    assert ah.ARCHIVE_HOSTS == RULED_HOSTS and ah.ARCHIVE_PATH_PREFIXES == RULED_PATH_PREFIXES
    assert ah.STRIP_WWW is True  # ruling 3 b
    assert ah.ARCHIVE_HOST_LIST_VERSION == "g3o.archive_hosts.v2"
    assert ah.host_list_sha256() == ah.ARCHIVE_HOST_LIST_SHA256
    assert ah.setup_record() == {"version": "g3o.archive_hosts.v2", "sha256": ah.ARCHIVE_HOST_LIST_SHA256,
                                 "hosts": sorted(RULED_HOSTS), "path_prefixes": {"archive.org": ["/details/"]},
                                 "strip_www": True}


def test_hash_changes_with_the_list():
    assert ah.host_list_sha256(ah.ARCHIVE_HOSTS | {"archive.example"}) != ah.ARCHIVE_HOST_LIST_SHA256
    assert ah.host_list_sha256(path_prefixes={}) != ah.ARCHIVE_HOST_LIST_SHA256
    assert ah.host_list_sha256(strip_www=False) != ah.ARCHIVE_HOST_LIST_SHA256


@pytest.mark.parametrize("url", [
    "https://web.archive.org/web/20230101000000/https://www.example.gov/ai",
    "http://wayback.archive.org/web/2022/https://x.gov/",
    "https://archive.ph/AbCdE", "https://archive.is/AbCdE", "https://archive.today/AbCdE",
    "https://archive.li/AbCdE", "https://archive.md/AbCdE", "https://archive.vn/AbCdE",
    "https://webcache.googleusercontent.com/search?q=cache:https://x.gov/",
    "HTTPS://WEB.ARCHIVE.ORG/web/2023/x",  # lowercased
    "https://web.archive.org:443/web/2023/x",  # port is not part of the host
    "https://user:pw@archive.ph/x",  # userinfo dropped
    "https://web.archive.org./web/2023/x",  # trailing root dot
    "https://www.archive.ph/x",  # ruling 3 b: leading www. dropped
    "https://WWW.web.archive.org/web/2023/x",
    "https://archive.fo/x",  # ruling 4 b
    "https://archive.org/details/some-item",  # ruling 4 b: item pages
    "https://www.archive.org/details/some-item",
])
def test_archive_addresses(url):
    assert ah.is_archive_address(url) is True
    assert sf.source_archive_address(url) is True


@pytest.mark.parametrize("url", [
    "https://www.example.gov/ai",
    "https://archive.org/",  # archive.org counts only under /details/
    "https://archive.org/search?query=x",
    "https://archive.org/detailsx/y",  # prefix is the whole path segment
    "https://foo.web.archive.org/x",  # no subdomain matching
    "https://www2.archive.ph/x",  # only a leading www. is dropped
    "https://web.archive.org.evil.example/x",  # no prefix matching
    "https://notarchive.ph/x",  # no suffix matching
    "https://cache.googleusercontent.com/x",
    "https://example.gov/https://web.archive.org/web/2023/x",  # archive host only in the path
])
def test_not_archive_addresses(url):
    assert ah.is_archive_address(url) is False


@pytest.mark.parametrize("url", ["", "   ", "web.archive.org/web/2023/x", "not a url", None])
def test_url_without_host_is_refused(url):
    with pytest.raises(ValueError, match="no host"):
        ah.is_archive_address(url)


def _official(value):
    return sf.FieldValue(sf.OFFICIAL, value, "mechanical", "test")


@pytest.mark.parametrize(("official", "url", "route"), [
    ("not_official", "https://web.archive.org/web/2023/https://x.gov/", sf.AUTO_ARCHIVE),
    ("not_official", "https://news.example.com/story", None),
    ("unknown", "https://archive.ph/AbCdE", sf.AUTO_ARCHIVE),
    ("own_official", "https://archive.ph/AbCdE", sf.AUTO_OFFICIAL),  # official is tested first
])
def test_route_from_the_page_url(official, url, route):
    assert sf.route_source_type(_official(official), sf.source_archive_address(url)) == route
