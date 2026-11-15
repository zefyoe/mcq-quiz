# Private patient invoicing

The invoice list and its API are restricted to administrators under
`/admin/appointments/invoices`. Nothing is included in public agenda templates.
The existing independent practice database stores settings, drafts, issued PDF
snapshots, numbering and delivery receipts. No additional hosting service is used.

## First use

Open **Factures → Paramètres du cabinet**. Supply the actual legal issuer, BCE,
radiologist/INAMI, billing address, IBAN, account holder and applicable convention
status. Bank and contact details are entered in the authenticated UI, never Git.
IBAN and Belgian enterprise check digits are validated. Issuance is blocked while
required issuer details are absent.

From a booking, patient list or historical dossier, **Créer une facture** adds one
idempotent draft for that examination. Fill the patient's home address, verify the
examination/INAMI code and insurer, and adjust amounts where appropriate. A changed
code offers the existing 2026 normal-status tariff reference; it is not a live
MyCareNet tariff or an eligibility check. A consultation is not added automatically.

The default **patient amount is EUR 20**, adjustable with **Adapter les montants**.
It is not declared to be the statutory ticket modérateur. The draft separately
records the statutory ticket, any patient supplement and the insurer's share.
The doctor must verify the rights and applicable tariff. Supplementary charges
for the covered reimbursable BIM examinations are blocked by this workflow.

After confirming the examination was performed, **Émettre la facture** allocates
one sequential annual number and stores the immutable PDF and issuer snapshot.
It uses the actual issue date and a due date 30 days later. Future examinations
remain drafts. Changing a bank account later does not rewrite old invoices.
Issued documents cannot be edited or silently deleted; credit-note workflows are
not implemented. Drafts can still be completed and corrected.

## Mail and follow-up

**Envoyer la facture PDF** uses the current administrator's existing Gmail
connection. The address and patient's acceptance must be confirmed. Each request
has a persistent receipt; repeated requests do not send again. A deliberate resend
requires a separate confirmation. If Gmail does not confirm the outcome, sending
is locked until the administrator checks Sent and explicitly reactivates it.
A pending request cannot be reset during its first two minutes. Provider acceptance
is not proof of final delivery/read receipt. No automatic reminders are sent.

Payments are marked manually after checking the bank account. Payment tracking
never changes the original PDF. A draft follows appointment moves and conversion
from a reservation to a confirmed booking. Recovery from appointment trash retains
the invoice association and immutable issued documents.

This is a **patient invoice/fee-letter workspace**, not a certified eFact/eAttest
connection. Insurer transmission must happen separately through the practice's
appropriate MyCareNet-enabled software. The insurer share is displayed separately
and is never requested as a bank transfer from the patient.

## Verification

`python scripts/smoke_test_invoices.py` uses temporary databases and mocked mail.
It checks privacy/CSRF, numbering, concurrency, duplicate requests, frozen PDFs,
30-day dates, editable EUR 20 default, tariff references, BIM guards, settings
snapshots, uncertain-send recovery and links across moves/historical records.
`--pdf-example` creates a non-payable specimen under ignored `output/pdf/`.
`--serve` starts a disposable local preview with fictional patients on port 5059;
there is no live Gmail connection in that preview.
