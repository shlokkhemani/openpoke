"""English stopwords shared by the BM25 query (server) and the eval word-splitting helpers."""
from __future__ import annotations

STOPWORDS = frozenset(
    "a an and are as at be but by for from had has have he her his how i if in into is it its me my of on or our "
    "she so than that the their them then they this to up us was we were what when where which who why will with "
    "you your about re any did do does not no yes can could would should s t d m ll ve don doesn didn isn aren wasn won".split())
