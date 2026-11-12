# WIRC — wirc.be

## Prepared behavior

- Former public `/agenda`: French temporary closure, no reopening date, no WIRC
  URL, link, redirect or notification to former patients.
- Direct public booking/hold/draft POSTs: HTTP 423 without a database write.
- Former internal agenda: existing accounts, appointments, reports, requests,
  registers, documents and recoverable trash stay available in the former database.
- WIRC: separate service, separate database, separate secret and sessions; no
  patient, document, user, password or Gmail-token import. No old location in new
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
3. Create the new service and database from this separate Blueprint. Do not
   clone/restore the former database or copy its `DATABASE_URL`/`SECRET_KEY`.
   `PRACTICE_PROFILE=wirc` requires `WIRC_DATABASE_URL`; it refuses the default old
   database setting. Leave public booking disabled (`APPOINTMENT_BOOKING_ENABLED=0`).
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
7. Enter the new `APPOINTMENT_PRACTICE_ADDRESS`; review opening hours, upload,
   reporting/PDF and recovery with fictitious data. WIRC refuses public booking
   activation while its address is missing. Activate booking explicitly when
   ready. There is no automatic reopening date.

## Local verification

`python scripts/smoke_test_practice_transition.py` checks the former closure,
retained internal records, blocked POSTs and the isolated WIRC profile in separate
temporary databases. `--serve` previews the closure on localhost:5058; `--wirc
--serve` previews WIRC with a fictitious administrator, `y@bymed.be` /
`test-password`. The test database is removed on exit.
