# WIRC — wirc.be

## Prepared behavior

- Former public `/agenda`: French temporary closure, no reopening date, no WIRC
  URL, link, redirect or notification to former patients.
- Direct public booking/hold/draft POSTs: HTTP 423 without a database write.
- Former internal agenda: existing accounts, appointments, reports, requests,
  registers, documents and recoverable trash stay available in the former database.
- WIRC: separate service, separate database, separate secret and sessions; no
  patient, document or Gmail-token import. The owner requested reuse of the two
  allowlisted administrator logins and Google sign-in. No other users are copied. No old location in new
  PDF/mail headers. The former application's `render.yaml` is unchanged.
- WIRC contains the existing scheduling, admin hours, drag/move/trash, reporting,
  PDF, request uploads, XIMEO-RIZIV and Gmail integration features. Student quiz,
  registration and payment routes are unavailable in the WIRC profile.

## Launch steps still needed

1. The owner selected `wirc.be` at Wix. Verify ownership/registration in that
   account. This code change does not purchase, transfer or register a domain.
2. Review the resource plans in `deploy/wirc.render.yaml.example`. It is a draft
   for a **new** Render Blueprint, not a modification of the former service.
   Resource creation incurs the selected hosting charges. Render documents the
   format in its [Blueprint reference](https://render.com/docs/blueprint-spec).
   Do not store patient data in a trial database: Render's
   [free database expires after 30 days](https://render.com/docs/free).
   The owner authorized up to €20/month for the new application and database.
   The initial database is capped at 5 GB with automatic storage growth disabled;
   check the live Render estimate before creating resources or increasing limits.
3. Create the new service and database from this separate Blueprint. Do not
   clone/restore the former database or copy its `DATABASE_URL`/`SECRET_KEY`.
   `PRACTICE_PROFILE=wirc` requires `WIRC_DATABASE_URL`; it refuses the default old
   database setting. The WIRC Blueprint now enables public booking at Centre
   Médical Azalys, Lenneke Marelaan 12, 1932 Woluwe-Saint-Étienne, with Thursday
   08:00–12:00 only, in ten-minute slots. The existing two-adjacent-slot release
   policy is preserved. Legacy Bymed remains publicly closed.
4. In the new service's shell, run `python scripts/create_wirc_admin.py`. Enter
   an approved admin address and a new password interactively. No credentials
   belong in this file, Git, a command argument or chat.
5. Add `wirc.be` to the **new** Render service; use the exact DNS values shown by
   Render at the registrar, then verify HTTPS. Do not add it to the former
   service. Follow [Render's domain instructions](https://render.com/docs/custom-domains).
6. Add `https://wirc.be/auth/google/callback` to the Google OAuth client's
   authorized redirect URIs after domain ownership is verified. Configure the
   new service's Google client variables privately. Log in/connect Gmail anew;
   former encrypted Gmail credentials are deliberately not transferred.
7. Review opening hours, upload, reporting/PDF and recovery with fictitious data.
   WIRC refuses public booking activation while its address is missing. The old
   practice has no automatic reopening date and receives no link to WIRC.

## Local verification

`python scripts/smoke_test_practice_transition.py` checks the former closure,
retained internal records, blocked POSTs and the isolated WIRC profile in separate
temporary databases. `--serve` previews the closure on localhost:5058; `--wirc
--serve` previews WIRC with a fictitious administrator, `y@bymed.be` /
`test-password`. The test database is removed on exit.
