# Integration request triage

Feedback is evidence for prioritization, not a commitment to implement every requested integration. Keep requests in the portable core only when the same capability is useful across providers and frameworks; vendor-specific behavior belongs in an adapter or a namespaced extension until a cross-provider use case is demonstrated.

## Review rubric

For each request, record an outcome and assess:

1. **Repeated demand:** number of independent requests and whether teams describe the same workflow.
2. **Migration impact:** how many users are blocked or need manual work, and how severe that loss is.
3. **Core relevance:** whether the capability generalizes across tools or is specific to one vendor/runtime.
4. **Testability and ownership:** whether maintainers can create conformance cases, document the boundary, and support the adapter over time.
5. **Source rights and sensitivity:** whether a sanitized fixture is available with permission to publish and contains no secrets, customer data, or proprietary prompts.

Do not score request volume without reviewing the workflow and licensing constraints. A single severe, reproducible blocker can justify an example or adapter investigation, but not automatically a normative format change.

## Disposition labels

- `needs-example`: current behavior is adequate, but users need a clearer recipe or documented limitation.
- `candidate-adapter`: a concrete source/target integration is repeated or blocks meaningful migrations and can be maintained outside the portable core.
- `candidate-format-extension`: a capability has a cross-provider use case, stable semantics, a conformance fixture, and a migration story. Keep it namespaced until compatibility is demonstrated.
- `out-of-scope`: the request depends on proprietary data, unsupported runtime behavior, or a vendor-specific workflow with no portable contract.

Before accepting a normative capability, require either a real sanitized fixture with public-use permission or a documented workflow that independent users can reproduce. Fixture sharing is optional; requests without a fixture can still be triaged as `needs-example` or `candidate-adapter`.

## Deferred: `okf-aget`

The earlier `okf-aget` mention remains unprioritized. Its identity, repository, interface, and intended workflow have not been confirmed in this project context. Do not create a dependency or design an integration until those details and a concrete use case are available. Reassess it using this same rubric when that evidence exists.
