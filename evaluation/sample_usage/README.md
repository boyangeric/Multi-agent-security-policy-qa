# Multi-Agent Security Policy Q&A — Sample Usage

Text examples for the `policy-qa` CLI. The policy answer and fallback below
come from the committed evaluation traces; they are excerpts, not a new live run.
The capabilities example uses the deterministic response defined in the code.

## Grounded policy answer

Source: [recorded trace](../results/what-controls-apply-to-api-security.json).

```text
policy-qa ask "What controls apply to API security?"

MULTI-AGENT SECURITY POLICY Q&A
Status: SUCCESS

Controls from the provided set that apply to API security (supported aspects
  only):

- Protect API traffic using cryptographic mechanisms to ensure confidentiality
  and integrity (e.g., TLS/IPSec; use of hashes, MACs, digital signatures to
  detect modification) (SC-8(1)).

- Log and review API-related activity: review and analyze audit records for
  inappropriate or unusual activity, report findings to appropriate roles, and
  adjust audit review based on changes in risk; include monitoring of
  communications at system interfaces in logging (AU-6).

- Enforce least privilege for API access and processing: permit only authorized
  accesses (users and processes) necessary to accomplish tasks; apply least-
  privilege in development, implementation, and operation of systems that
  provide the API (AC-6).

- Engineer APIs and their components to support least privilege: design
  interfaces and internal component structure so privileges are fine-grained and
  components have only the privileges needed; require developers to structure
  hardware/software/firmware to facilitate access control by least privilege
  (SA-8(14); SA-17(7)).

Limits of coverage: the retrieved controls cover encryption for transmission,
  auditing, and least-privilege design/engineering. They do not provide explicit
  controls in this set for API-specific topics such as authentication/token
  management, input validation, rate limiting, API gateways, or client-side
  security; those topics are not addressed in the provided controls.

Citations: SC-8(1), AU-6, AC-6, SA-8(14), SA-17(7)
Grounded: True
```

## Out-of-domain fallback

Source: [recorded trace](../results/what-is-the-best-recipe-for-chocolate-chip-cookies.json).

```text
policy-qa ask "What is the best recipe for chocolate chip cookies?"

MULTI-AGENT SECURITY POLICY Q&A
Status: FALLBACK (out_of_domain)

This question falls outside the indexed security policy corpus (NIST SP 800-53
  Rev 5), so no answer was attempted. Please ask about enterprise security
  policy — for example access control, logging and monitoring, or incident
  response.

Citations: -
Grounded: False
```

## Capabilities

```text
User > What can you do?

I am an enterprise security policy assistant. My knowledge base is the NIST SP
  800-53 Rev 5 security control catalog, indexed in Azure AI Search and spanning
  control families such as Access Control, Audit and Accountability, and System
  and Communications Protection. Ask me about security policy requirements — for
  example access control, logging and monitoring, or data protection — and I
  will answer strictly from the retrieved controls, with citations. I cannot
  answer questions outside this catalog.
```
