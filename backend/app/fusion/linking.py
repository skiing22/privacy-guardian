"""Entity linking (FR-13): which spans in one document are the same real thing.

Two steps, with union-find so links are transitive:
1. Exact: same type and same normalized value ("98470 12345" == "+91 9847012345").
2. Partial names: a short PERSON mention ("Rahul", "Mr. Sharma", "R. Sharma") joins the one
   full name it fits. If it fits several ("Reddy" with Vikram and Sneha Reddy), it is
   ambiguous and stays alone, because a wrong link would merge two real people.
"""

from dataclasses import dataclass

from app.detectors.types import PiiType, Span
from app.fusion.normalize import name_tokens, normalize


@dataclass(frozen=True)
class Entity:
    id: str  # e.g. "PERSON_1"
    pii_type: PiiType
    canonical: str  # longest mention text
    mentions: tuple[int, ...]  # indexes into the input span list
    ambiguous: bool = False


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path halving
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)  # keep earliest as root


def _fits(short: list[str], full: list[str]) -> bool:
    """Every short token matches a different full token; a one-letter token is an initial."""
    used: set[int] = set()
    for s in short:
        for i, f in enumerate(full):
            if i not in used and (s == f or (len(s) == 1 and f.startswith(s))):
                used.add(i)
                break
        else:
            return False
    return True


def link(spans: list[Span]) -> list[Entity]:
    n = len(spans)
    uf = _UnionFind(n)
    keys = [normalize(s.text, s.pii_type) for s in spans]

    first: dict[tuple[PiiType, str], int] = {}
    for i, s in enumerate(spans):
        k = (s.pii_type, keys[i])
        if k in first:
            uf.union(first[k], i)
        else:
            first[k] = i

    persons = [i for i, s in enumerate(spans) if s.pii_type is PiiType.PERSON and keys[i]]
    toks_of = {i: name_tokens(spans[i].text) for i in persons}
    # a "full" name has 2+ parts and no initials; only full names can absorb mentions
    full = [i for i in persons if len(toks_of[i]) >= 2 and all(len(t) > 1 for t in toks_of[i])]
    ambiguous: set[int] = set()
    for i in persons:
        toks = toks_of[i]
        cands = {
            uf.find(j)
            for j in full
            if toks_of[j] != toks and len(toks_of[j]) >= len(toks) and _fits(toks, toks_of[j])
        }
        if len(cands) == 1:
            uf.union(cands.pop(), i)
        elif len(cands) > 1:
            ambiguous.add(i)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    counters: dict[PiiType, int] = {}
    out: list[Entity] = []
    for root in sorted(groups):
        members = groups[root]
        t = spans[root].pii_type
        counters[t] = counters.get(t, 0) + 1
        canonical = max((spans[m].text for m in members), key=len)
        out.append(
            Entity(
                id=f"{t.value}_{counters[t]}",
                pii_type=t,
                canonical=canonical,
                mentions=tuple(members),
                ambiguous=any(m in ambiguous for m in members),
            )
        )
    return out
