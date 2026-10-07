# LTM Conflict Evidence

| Layer | "Python" (old fact) | "Rust" (new fact) | Superseded? | Evidence |
|---|---|---|---|---|
| Structured memory | Superseded | Active | Yes | Same slot; Python.superseded_by → Rust |
| Retrieval filter | Excluded | Eligible | Yes | Python filtered: status=superseded |
| Final retrieval | Not selected | Selected (0.88) | Yes | Rust is the only selected candidate |
| Final LTM context | Absent | Present | Yes | Memory block contains Rust only |

Takeaway: The LTM system structurally supersedes the old fact and removes it before retrieval, rather than relying on the model to interpret conflicting history.
