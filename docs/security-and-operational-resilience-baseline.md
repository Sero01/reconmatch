# Security and Operational Resilience Baseline

> Target: a defensible production baseline for a reconciliation application handling financial records. It is not a claim of “leak-proof” security or certification.

## 1. Threat model

| Asset | Threats | Primary controls |
|---|---|---|
| Uploaded bank/ERP evidence | Unauthorized access, tampering, malicious file, deletion. | Authenticated upload, content/size validation, malware scanning, encrypted immutable store, access logs, retention/backup. |
| Transaction/case data | Cross-tenant leak, bulk export, injection, accidental disclosure. | Server-side tenant authorization, RBAC/ABAC, field masking, rate limits, secure queries/output encoding, DLP/export policy. |
| Match/rule decisions | Unauthorized rule change, forged approval, non-reproducible result. | Versioned rules, maker-checker, audit events, frozen run inputs, release/change approval. |
| Credentials/integrations | Secret leak, overbroad account access, replay. | Secret manager, short-lived/least-privilege credentials, rotation, egress controls, idempotency/correlation. |
| Audit trail | Deletion, alteration, sensitive log leakage. | Append-only sink, restricted writer/reader roles, hash checkpoints, redaction, time sync, monitoring. |
| Availability | Ransomware, outage, queue retry duplication, bad deployment. | Immutable backups, restore drills, multi-zone service, transactional/idempotent processing, deployment rollback. |

NIST CSF 2.0 organizes cybersecurity outcomes under Govern, Identify, Protect, Detect, Respond, and Recover. [NIST CSF 2.0](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=957258)

## 2. Security architecture baseline

```text
Internet -> WAF/rate limit -> API/UI -> authorization policy -> application services
                                            |              -> encrypted relational store
SSO/OIDC + MFA -----------------------------+              -> object/evidence store
connector workers (private egress allowlist) -> queue/outbox -> audit/security log sink
```

### Identity and authorization

- Use OIDC/SAML SSO; require phishing-resistant MFA for privileged and approval roles.
- Use server-side policy checks on every read/write/export: tenant, legal entity, recon definition, account/book, action, data classification.
- Separate roles: viewer, preparer, reviewer, rule approver, source operator, journal approver, tenant admin, security auditor, support.
- Enforce SoD relationships dynamically (e.g. `actor != proposer` on review) and review privileged memberships periodically.
- Use service identities per connector/workload, not shared user credentials.

### Data protection

- TLS in transit; encryption at rest via managed KMS; rotate keys and document ownership.
- Keep evidence, database backups, search indexes, logs, and exports within the same classification/retention design.
- Tokenize/mask payment-card and sensitive personal fields; never log secrets/session tokens/full PAN.
- Prefer content-addressed evidence ID and opaque object keys over meaningful filesystem paths.
- Apply GDPR purpose limitation/minimisation/retention where applicable. [GDPR Article 5](https://eur-lex.europa.eu/legal-content/EN/TXT/?toc=OJ%3AL%3A2016%3A119%3AFULL&uri=uriserv%3AOJ.L_.2016.119.01.0001.01.ENG)

### File and integration safety

- Allowlist formats, size, number of files, compression ratio, and schema; validate content rather than trusting extension.
- Parse untrusted files in a constrained worker; do not execute macros/formulas; neutralize CSV formula injection in exports.
- Scan uploads and archives before availability; never serve raw uploads from a web-executable path.
- Use outbound allow lists and signed/validated webhooks where supported.

OWASP ASVS requires file-size and content-type protections and bounds on archive expansion. [OWASP ASVS file handling](https://cornucopia.owasp.org/taxonomy/asvs-5.0/05-file-handling/02-file-upload-and-content)

## 3. Audit/security logging

Security events: authentication, authorization denials, privileged role/rule/config changes, export/download, connector credential use/failure, upload/malware result, secret access, deployment, and suspicious rate/activity alerts.

Business audit events: source received/quarantined, parser/mapping change, rule activated, candidate/match disposition, manual action, approval, attestation, journal proposal/posting, reopen, and deletion/retention action.

Log metadata: UTC time, actor, tenant, request/correlation ID, action, target, outcome, source IP/device where policy permits, before/after hashes, and relevant version IDs. OWASP requires sufficient “when, where, who, what” metadata, synchronized time, correlatable logs, and sensitivity-aware logging. [OWASP ASVS logging](https://cornucopia.owasp.org/taxonomy/asvs-5.0/16-security-logging-and-error-handling/02-general-logging)

NIST describes log management as generating, transmitting, storing, accessing, and disposing of logs to investigate incidents and operational issues. [NIST log-management planning](https://csrc.nist.gov/pubs/sp/800/92/r1/ipd)

## 4. Secure delivery baseline

| Stage | Required gate |
|---|---|
| Design | Threat model, data classification, auth matrix, abuse cases, retention and recovery objectives. |
| Code | Review, dependency lock/SBOM, secret scanning, SAST, tests for tenant/SoD boundaries. |
| Build | Reproducible artifact, signed/provenanced artifact where possible, isolated CI credentials. |
| Deploy | IaC review, environment separation, least-privilege runtime identity, configuration/secret validation. |
| Operate | Vulnerability/patch process, monitored alerts, access review, backup/restore drill, incident exercise. |

Use OWASP ASVS 5.0 as a testable verification catalogue; it covers architecture, authentication, access control, validation, cryptography, logging, data protection, API and configuration requirements. [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)

## 5. Resilience and recovery

Define objectives by reconciliation criticality:

- **RPO:** maximum source/match/case/audit event loss accepted.
- **RTO:** time to restore service and process backlog.
- **MTPD/cut-off:** latest acceptable result for operational/close decisions.

Design for evidence replay: raw source evidence + parser/mapping + reference/rule/engine versions must reconstruct canonical records and decisions. Test restores into an isolated environment; verify hash/count/totals, then rerun selected reconciliations. A backup that has not been restored is an assumption, not a control.

Ensure queues are at-least-once safe: idempotency keys and transactional outbox/inbox semantics prevent duplicate state/matches during retries. A failed worker must leave a detectable recoverable state, never a silently partial reconciliation.

## 6. First implementation checklist

- [ ] Threat model and data classification recorded for CSV upload/demo and future bank connector.
- [ ] OIDC/MFA, tenant/role model, and server-side authorization tests before multi-user access.
- [ ] Evidence storage, database, and backups encrypted; secrets leave code/config files.
- [ ] Upload size/type/schema controls, quarantine, and safe export escaping.
- [ ] Structured business/security audit events with redaction, immutable retention, and alerting.
- [ ] Versioned rules/configuration plus maker-checker activation.
- [ ] Dependency/deployment scanning and incident/restore runbook.
- [ ] Restore/replay drill demonstrated before declaring production readiness.
