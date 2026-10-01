---
format: opf/0.1
id: conformance.sample
version: 1.2.3
description: Shared parser and renderer fixture.
tags:
  - conformance
  - on
  - 2026-10-02
inputs:
  customer_message:
    type: string
    required: true
---

## system
Respond to the customer. Preserve the supplied text literally.

## developer
Use a helpful tone.

## user
Customer says: {{ customer_message }}

This heading is content:
### user

```md
## assistant
That heading is inside a code fence.
```

\## assistant
