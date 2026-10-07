# LTM Privacy Evidence

| Data | Classification | LTM Decision | Stored? | Evidence |
|---|---|---|---|---|
| Email address | CONTACT:EMAIL | REJECT | No | Contact identifier excluded from LTM |
| API key | SECRET:API_KEY | SCRUB + REJECT | No | Secret removed before durable memory / model reuse |
| “Concise emails” preference | Preference | STORE | Yes · ACTIVE | Retrieved for the later email-draft request |
| Final LTM context | Safe preference only | SELECTED | Yes | No email or API key in the memory block |

Takeaway: The LTM system separates useful personalization from sensitive data — secrets and contact identifiers are blocked from long-term memory, while the safe preference is retained and retrieved.
