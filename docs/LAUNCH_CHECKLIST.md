# Controlled private-alpha launch checklist

Implemented engineering and remaining operator/external work are separate. This checklist does not authorize invitations or public deployment.

## Implemented and exercised locally

- [x] Preserve M3; isolate M4 branch; no merge into main.
- [x] Invite/disabled enrollment, first-admin lock, credential expiry/rotation/revocation and tenant/export boundaries.
- [x] Isolated parsers, CPU/memory/wall failures and Linux file/network/process controls.
- [x] Concurrent quota/request/provider reservations, private HTTPS/resource limits and log rotation.
- [x] Safe request IDs/logs, aggregate diagnostics and readiness.
- [x] Encrypted hosted backup restored into a separate empty environment with matching sources/citations; unsafe restores refused.
- [x] Audited review/correction workflow and frozen evaluation modes; human/holdout scores left empty.
- [x] Onboarding/sample/tutorials/troubleshooting, five pilot tasks and empty feedback measurements.
- [x] Record final standalone recovery, worker interruption, desktop/mobile screenshot inspection and all-six-job CI evidence in [the M4 audit](MILESTONE4_AUDIT.md).

## Required operator steps before invitations

- [ ] Obtain user authorization for participants and invitation delivery. None have been invited automatically.
- [ ] Agree permitted data, consent, incident owner, private reporting and deletion/retention policy.
- [ ] Approve private/VPN network, trusted hostname/TLS and firewall; verify blocked DB/API exposure from a pilot machine.
- [ ] Replace development secrets; verify secure cookies, closed registration and public-widget prohibition; securely initialize operator access.
- [ ] Verify strict Linux containment/readiness/model hashes; review dependency and image vulnerabilities.
- [ ] Schedule encrypted off-host backups, secure separate recovery secrets, set retention and restore on the target host.
- [ ] Set readiness/disk/resource/queue/5xx alerts and operator response; review document/rebuild caps and credential rotation.
- [ ] Keep hosted providers disabled unless separately authorized, with provider-side billing and application usage caps.
- [ ] Conduct actual human label review and collect unused holdout cases; avoid synthetic accuracy marketing.
- [ ] Run an authorized small pilot and measure real timings, errors, assistance and difficulty before expanding access.

## Future work, not claimed complete

Independent audit/penetration test; stronger parser VM/container isolation and malware/CDR scanning; managed secrets/identity/reset/verification/SSO; physical per-tenant DB/index accounting; source-orphan/history retention automation; managed monitoring/HA; general prompt-injection/entailment defenses and customer-data quality studies. No production certification or public launch is claimed.
