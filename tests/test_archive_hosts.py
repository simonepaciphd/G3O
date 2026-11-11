"""Tests for the versioned archive-host list (PI ruling A2.1 a, 2026-11-11).

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
    "webcache.googleusercontent.com",
}


def test_list_is_the_ruled_list_with_its_version_and_hash():
    assert ah.ARCHIVE_HOSTS == RULED_HOSTS
    assert ah.ARCHIVE_HOST_LIST_VERSION == "g3o.archive_hosts.v1"
    assert ah.host_list_sha256() == ah.ARCHIVE_HOST_LIST_SHA256
    assert ah.setup_record() == {"version": "g3o.archive_hosts.v1", "sha256": ah.ARCHIVE_HOST_LIST_SHA256,
                                 "hosts": sorted(RULED_HOSTS)}


def test_hash_changes_with_the_list():
    assert ah.host_list_sha256(ah.ARCHIVE_HOSTS | {"archive.fo"}) != ah.ARCHIVE_HOST_LIST_SHA256


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
])
def test_archive_addresses(url):
    assert ah.is_archive_address(url) is True
    assert sf.source_archive_address(url) is True


@pytest.mark.parametrize("url", [
    "https://www.example.gov/ai",
    "https://archive.org/details/some-item",  # not listed: only the Wayback hosts are
    "https://www.archive.ph/x",  # exact match: no www. stripping
    "https://foo.web.archive.org/x",  # no subdomain matching
    "https://web.archive.org.evil.example/x",  # no prefix matching
    "https://notarchive.ph/x",  # no suffix matching
    "https://archive.fo/x",  # archive.today alias not in the ruled list
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
