# ReplayMark E3b shadow runtime bridge freeze

## Status

This increment closes exactly one boundary after the independently frozen E3b
realizers and same-task correlator:

```text
E3bCorrelatedRuntimePair
  -> existing ExplicitCompiledContract.adjudicate(...)
  -> existing ExplicitCompiledContract.certify_reuse(...)
  -> RuntimeReuseCertificate
  -> E3bShadowRuntimeReuseCertificate
```

It remains **shadow only**. It does not execute, block, publish, regenerate, or
choose fallback policy.

## Why the final wrapper exists

`RuntimeReuseCertificate` binds a realized observation/action pair to a
contract/claim adjudication and R* result, but the E3b same-task proof is
substrate-specific and intentionally remains outside that generic type.

Returning only the generic certificate would allow the correlation proof to
become detached from the serialized end-to-end audit object. This increment does
not mutate the frozen generic type. Instead the thin E3b-specific
`E3bShadowRuntimeReuseCertificate` embeds both the exact correlated pair and the
exact generic semantic certificate.

The wrapper cross-checks contract fingerprint, claim fingerprint, realized
observation fingerprint, and realized historical-action fingerprint.

## Production rule

The production function accepts only:

```text
ExplicitCompiledContract
E3bCorrelatedRuntimePair
```

It cannot accept raw runtime records or separately realized values. Realization
and same-task correlation are therefore mandatory preconditions.

Its only semantic calls are:

```text
contract.adjudicate(token, historical_action)
contract.certify_reuse(token, historical_action)
```

There is no local support-envelope lookup, Verdict implementation, R* logic,
world enumeration, counterexample search, or claim projection algorithm.

## Failure separation

The chain preserves:

```text
realization failure
  != same-task correlation failure
  != semantic VALID / INVALID / UNRESOLVED
```

and:

```text
R* DO_NOT_REUSE
  != execute fallback
  != regenerate
  != abort
```

This increment stops at certification.

## Verification obligations

The gate verifies:

1. existing contract `VALID / REUSE` is preserved exactly;
2. existing contract `INVALID / DO_NOT_REUSE` is preserved exactly;
3. existing contract `UNRESOLVED / DO_NOT_REUSE` is preserved exactly;
4. embedded adjudication and R* bytes equal direct frozen-contract outputs;
5. cross-task pairs fail before semantic certification;
6. malformed realization input fails before semantic certification;
7. a semantic certificate cannot be reattached to another correlation proof;
8. claim and contract bindings are cross-checked in the chained certificate;
9. production source imports no adjudicator/R*/support implementation and has no
   publish/execute/fallback/regenerate call.

The existing observation, action, correlation, concrete-contract packaging,
adjudicator, and R* gates are rerun unchanged.

## Intentionally open

```text
R1 shadow hook                    NOT_IMPLEMENTED
execution byte/event equivalence  NOT_MEASURED
runtime latency/throughput        NOT_MEASURED
execution/fallback policy         NOT_IMPLEMENTED
selective-reuse intervention      NOT_IMPLEMENTED
```

The next boundary is a non-interfering R1 shadow hook that emits this certificate
while proving the legacy R1 execution trace remains unchanged.
