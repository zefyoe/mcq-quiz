"""INAMI ultrasound nomenclature and internal 2026 tariff snapshots.

Source: Echographies_INAMI_art17bis_2026.xlsx supplied by the practice.
Tariffs apply from 2026-01-01 to conventioned ambulatory care without
preferential status. Amounts are stored as integer euro cents and must never
be rendered in the appointment planner.
"""

INAMI_TARIFF_EFFECTIVE_DATE = "2026-01-01"
INAMI_CONSULTATION_CODE = "460795"


def _entry(
    code,
    label_fr,
    label_nl,
    n_value,
    exam_reimbursement_cents,
    exam_patient_share_cents,
    exam_total_cents,
    invoice_total_cents,
):
    return {
        "code": code,
        "label_fr": label_fr,
        "label_nl": label_nl,
        "n_value": n_value,
        "exam_reimbursement_cents": exam_reimbursement_cents,
        "exam_patient_share_cents": exam_patient_share_cents,
        "exam_total_cents": exam_total_cents,
        "consult_reimbursement_cents": 2705,
        "consult_patient_share_cents": 744,
        "consult_total_cents": 3449,
        "invoice_total_cents": invoice_total_cents,
    }


INAMI_ULTRASOUND_GROUPS = (
    (
        "Échographies bidimensionnelles — hors grossesse",
        "Bidimensionale echografieën — buiten zwangerschap",
        (
            _entry("460051", "Contenu du crâne, transfontanellaire", "Schedelinhoud, transfontanellair", "N 53", 4021, 248, 4269, 7718),
            _entry("460095", "Du cou (y compris tissus mous et ganglions cervicaux)", "Hals (inclusief weke delen en cervicale lymfeklieren)", "N 42", 3135, 248, 3383, 6832),
            _entry("460110", "Du thorax / paroi thoracique (y compris plèvre)", "Thorax / thoraxwand (inclusief pleura)", "N 30", 2168, 248, 2416, 5865),
            _entry("460154", "Abdomen : foie et/ou vésicule biliaire et/ou voies biliaires", "Abdomen: lever en/of galblaas en/of galwegen", "N 40", 2974, 248, 3222, 6671),
            _entry("460176", "Abdomen : pancréas et/ou rate", "Abdomen: pancreas en/of milt", "N 40", 2974, 248, 3222, 6671),
            _entry("460191", "Abdomen : reins et/ou surrénales et/ou rétropéritoine et/ou vaisseaux", "Abdomen: nieren en/of bijnieren en/of retroperitoneum en/of bloedvaten", "N 40", 2974, 248, 3222, 6671),
            _entry("460235", "Du bassin masculin", "Mannelijk bekken", "N 35", 2571, 248, 2819, 6268),
            _entry("460250", "Du bassin féminin", "Vrouwelijk bekken", "N 50", 3779, 248, 4027, 7476),
            _entry("460272", "Du scrotum", "Scrotum", "N 30", 2168, 248, 2416, 5865),
            _entry("460294", "D'un ou de plusieurs membres — échographie ostéo-articulaire et des tissus mous (épaule, genou, hanche, muscles, tendons…)", "Een of meerdere ledematen — osteo-articulaire en wekedelen-echografie (schouder, knie, heup, spieren, pezen…)", "N 42", 3135, 248, 3383, 6832),
            _entry("460611", "Échographie urinaire complète (non cumulable avec 460191/460235/460250)", "Volledige urinewegechografie (niet cumuleerbaar met 460191/460235/460250)", "N 60", 3940, 248, 4188, 7637),
        ),
    ),
    (
        "Échographies cardiovasculaires",
        "Cardiovasculaire echografieën",
        (
            _entry("460316", "Duplex couleur bilatéral des artères carotides", "Bilaterale kleurenduplex van de halsslagaders", "N 94", 7323, 248, 7571, 11020),
            _entry("460331", "Duplex couleur bilatéral des artères carotides et vertébrales", "Bilaterale kleurenduplex van de halsslagaders en vertebrale arteriën", "N 112", 7323, 248, 7571, 11020),
            _entry("460633", "Duplex couleur des vaisseaux profonds thoraciques/abdominaux/pelviens", "Kleurenduplex van de diepe thoracale, abdominale of bekkenvaten", "N 94", 7323, 248, 7571, 11020),
            _entry("461156", "Duplex couleur des vaisseaux artériels et/ou veineux des membres (max 1×/an civile)", "Kleurenduplex van de arteriële en/of veneuze vaten van de ledematen (max. 1×/kalenderjaar)", "N 60", 4653, 248, 4901, 8350),
            _entry("461355", "Duplex couleur des vaisseaux artériels des membres — follow-up/contrôle postop", "Kleurenduplex van de arteriële vaten van de ledematen — follow-up/postoperatieve controle", "N 30", 2203, 248, 2451, 5900),
            _entry("461370", "Duplex couleur des vaisseaux veineux des membres — follow-up/TVP", "Kleurenduplex van de veneuze vaten van de ledematen — follow-up/DVT", "N 30", 2203, 248, 2451, 5900),
            _entry("460375", "Duplex couleur des vaisseaux intracrâniens", "Kleurenduplex van de intracraniële bloedvaten", "N 83", 6437, 248, 6685, 10134),
        ),
    ),
    (
        "Échographies combinées",
        "Gecombineerde echografieën",
        (
            _entry("459712", "Examen abdominal total (foie, vésicule, rate, pancréas, reins/surrénales, rétropéritoine) — ≥8 coupes", "Volledig abdominaal onderzoek (lever, galblaas, milt, pancreas, nieren/bijnieren, retroperitoneum) — ≥8 coupes", "N 85", 6598, 248, 6846, 10295),
            _entry("459734", "Échographie urinaire complète (reins, uretères, vessie) — ≥6 coupes", "Volledige urinewegechografie (nieren, ureters, blaas) — ≥6 coupes", "N 70", 5390, 248, 5638, 9087),
            _entry("459756", "Duplex bilatéral carotides+vertébrales + duplex vaisseaux profonds/membres", "Bilaterale duplex carotiden+vertebrale arteriën + duplex diepe vaten/ledematen", "N 170", 13444, 248, 13692, 17141),
            _entry("459771", "Duplex bilatéral carotides+vertébrales + échographie d'une région", "Bilaterale duplex carotiden+vertebrale arteriën + echografie van één regio", "N 160", 12638, 248, 12886, 16335),
            _entry("459793", "Échographie d'au moins deux régions anatomiques différentes", "Echografie van minstens twee verschillende anatomische regio's", "N 70", 5390, 248, 5638, 9087),
            _entry("459815", "Duplex bilatéral des vaisseaux des membres + échographie d'une région", "Bilaterale duplex van de vaten van de ledematen + echografie van één regio", "N 160", 12638, 248, 12886, 16335),
        ),
    ),
    (
        "Élastographies",
        "Elastografieën",
        (
            _entry("461974", "Élastographie du foie (hépatite B/C active traitée, suivi fibrose, enfant <16 ans)", "Leverelastografie (behandelde actieve hepatitis B/C, fibroseopvolging, kind <16 jaar)", "N 30", 2168, 248, 2416, 5865),
            _entry("461996", "Échographie foie/vésicule/voies biliaires + élastographie du foie", "Echografie lever/galblaas/galwegen + leverelastografie", "N 70", 5390, 248, 5638, 9087),
        ),
    ),
)

INAMI_ULTRASOUND_BY_CODE = {
    entry["code"]: entry
    for _, _, entries in INAMI_ULTRASOUND_GROUPS
    for entry in entries
}
