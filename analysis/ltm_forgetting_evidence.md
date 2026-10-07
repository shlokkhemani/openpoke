# LTM Forgetting Evidence

| Stage | Result | Memory State | Retrieval | Evidence |
|---|---|---|---|---|
| Initial preference | STORE | ACTIVE | Eligible | Meeting preference stored |
| Forget request | DELETE | DELETED | Removed | Content purged and search entry removed |
| Tombstone | WRITE | Deleted slot protected | Blocked | Prevents deleted memory from being recreated |
| Final probe | NO MATCH | No active memory | 0 candidates | Empty LTM block |

Takeaway: Forgetting is a durable state transition — the memory is removed from retrieval and protected from being recreated.

Small caveat:
The original sentence may remain in same-session short-term conversation history until chat history is cleared.
