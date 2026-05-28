"""Regression tests for the reverse-engineered Firefox Places hash.

The expected values were read directly from a real places.sqlite, so these lock
the algorithm against ground truth.
"""
from heimdall.places_hash import hash_string, url_hash, rev_host


def test_scheme_hashes_match_observed():
    # High 16 bits of url_hash for these schemes, observed in a live DB.
    assert hash_string("https") & 0xFFFF == 11026
    assert hash_string("http") & 0xFFFF == 29222


def test_known_url_hash():
    # Row read from a real moz_places table.
    assert url_hash("https://support.mozilla.org/products/firefox") == 47358327123126


def test_url_hash_layout():
    u = "https://fmhy.net/"
    h = url_hash(u)
    assert (h >> 32) == (hash_string("https") & 0xFFFF)
    assert (h & 0xFFFFFFFF) == hash_string(u)


def test_rev_host():
    assert rev_host("fmhy.net") == "ten.yhmf."
    assert rev_host("support.mozilla.org") == "gro.allizom.troppus."
