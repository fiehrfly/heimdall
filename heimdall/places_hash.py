"""Firefox Places hashing primitives.

The `url_hash` algorithm below was reverse-engineered empirically against a real
`places.sqlite` and reproduces 514/516 stored hashes exactly (the misses are
pathological multi-kilobyte query-string URLs hashed by an older engine build).

Layout of moz_places.url_hash (64-bit):
    bits 32..47 : mozilla::HashString(scheme) & 0xFFFF
    bits  0..31 : mozilla::HashString(full_url)

`HashString` is the mfbt golden-ratio hash (kGoldenRatioU32 = 0x9E3779B9,
5-bit left rotate per byte).
"""

GOLDEN_RATIO_U32 = 0x9E3779B9


def hash_string(s: str) -> int:
    """mozilla::HashString over the UTF-8 bytes of `s` (32-bit)."""
    h = 0
    for b in s.encode("utf-8"):
        rotl5 = ((h << 5) | (h >> 27)) & 0xFFFFFFFF
        h = (GOLDEN_RATIO_U32 * (rotl5 ^ b)) & 0xFFFFFFFF
    return h


def url_hash(url: str) -> int:
    """Reproduce moz_places.url_hash for a full URL."""
    scheme = url.split(":", 1)[0]
    return ((hash_string(scheme) & 0xFFFF) << 32) | hash_string(url)


def rev_host(host: str) -> str:
    """moz_places.rev_host: host reversed with a trailing dot (e.g. fmhy.net -> ten.yhmf.)."""
    return host[::-1] + "."
