import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus


CORE_SECTIONS = (
    {"key": "chest", "label": "Chest Imaging", "label_nl": "Thoraxbeeldvorming"},
    {"key": "neuroradiology", "label": "Neuroradiology", "label_nl": "Neuroradiologie"},
    {"key": "pediatric", "label": "Pediatric Imaging", "label_nl": "Pediatrische beeldvorming"},
    {"key": "interventional", "label": "Interventional Radiology", "label_nl": "Interventieradiologie"},
    {"key": "genitourinary", "label": "Genitourinary Radiology", "label_nl": "Urogenitale radiologie"},
    {"key": "gastrointestinal", "label": "Gastrointestinal Imaging", "label_nl": "Gastro-intestinale beeldvorming"},
    {"key": "body-mri", "label": "Body MRI", "label_nl": "MRI van het lichaam"},
    {"key": "musculoskeletal", "label": "Musculoskeletal Imaging", "label_nl": "Musculoskeletale beeldvorming"},
    {"key": "emergency", "label": "Emergency Radiology", "label_nl": "Spoedradiologie"},
    {"key": "cardiac", "label": "Cardiac Imaging", "label_nl": "Cardiale beeldvorming"},
    {"key": "breast", "label": "Breast Imaging", "label_nl": "Borstbeeldvorming"},
    {"key": "labralis", "label": "LABRALIS", "label_nl": "LABRALIS", "placeholder_count": 1, "is_beta_demo": True},
)

DATA_DIRECTORY = Path(__file__).resolve().parent / "data"

ANSWER_SECTION_LABELS = {
    "findings": "Findings",
    "differential": "Differential Diagnosis",
    "teaching": "Teaching Points",
    "management": "Management",
    "references": "References",
}
ANSWER_SECTION_HEADINGS = {
    "findings": re.compile(r"^(Findings|Bevindingen)$", re.IGNORECASE),
    "differential": re.compile(r"^(Differential Diagnosis|Differentiaaldiagnose)$", re.IGNORECASE),
    "teaching": re.compile(r"^(Teaching Points|Kernpunten)$", re.IGNORECASE),
    "management": re.compile(r"^(Management|Beleid)$", re.IGNORECASE),
    "references": re.compile(r"^(Further Readings?|Referenties)$", re.IGNORECASE),
}

GU_DIFFERENTIAL_OVERRIDES_NL = {
    "CORE-GU-001": ["Heldercellig niercelcarcinoom", "Urotheelcarcinoom", "Lymfoom", "Oncocytoom"],
    "CORE-GU-002": ["Urotheelcarcinoom van het nierbekken", "Niercelcarcinoom", "Lymfoom"],
    "CORE-GU-003": ["Lymfoom", "Sarcoom", "Retroperitoneale fibrose", "Perinefrisch hematoom"],
    "CORE-GU-004": ["Lymfoom", "Metastasen", "Pyelonefritis"],
    "CORE-GU-005": ["Lymfoom", "Diabetes mellitus", "Acute glomerulonefritis", "Systemische lupus erythematodes", "Polyarteritis nodosa", "Granulomatose met polyangiitis"],
    "CORE-GU-006": ["Heldercellig niercelcarcinoom", "Papillair niercelcarcinoom", "Chromofoob niercelcarcinoom", "Oncocytoom", "Vetarm angiomyolipoom"],
    "CORE-GU-007": ["Urotheelcarcinoom", "Bloedstolsel"],
    "CORE-GU-015": ["Retroperitoneaal liposarcoom", "Groot exofytisch renaal angiomyolipoom"],
    "CORE-GU-016": ["Acute pyelonefritis", "Urinewegobstructie", "Nierveentrombose", "Niercontusie", "Vasculitis", "Hypotensie"],
    "CORE-GU-017": ["Niercyste", "Nierabces"],
    "CORE-GU-021": ["Diabetes mellitus", "Acute glomerulonefritis", "Vasculitis", "Lymfoom", "HIV-geassocieerde nefropathie"],
    "CORE-GU-022": ["Lymfoom", "Multifocaal papillair niercelcarcinoom", "Metastasen", "Infectie", "Sarcoïdose", "Granulomatose met polyangiitis"],
    "CORE-GU-023": ["Xanthogranulomateuze pyelonefritis", "Tuberculose"],
    "CORE-GU-024": ["Bosniak III-cyste", "Nierabces", "Renale hydatidecyste"],
    "CORE-GU-025": ["Medullaire nefrocalcinose", "Jichtnefropathie"],
    "CORE-GU-028": ["Eenvoudige niercyste", "Calyxdivertikel"],
    "CORE-GU-031": ["Atherosclerotische nierarteriestenose", "Fibromusculaire dysplasie"],
    "CORE-GU-032": ["Atherosclerotische nierarteriestenose", "Fibromusculaire dysplasie"],
    "CORE-GU-035": ["Perinefrisch hematoom", "Urinoom", "Lymfocele", "Abces"],
    "CORE-GU-039": ["Transplantaatafstoting", "Acute tubulusnecrose", "Nierveentrombose"],
    "CORE-GU-040": ["Hematoom", "Urinoom", "Lymfocele", "Abces"],
    "CORE-GU-041": ["Acute tubulusnecrose", "Acute transplantaatafstoting", "Chronische transplantaatafstoting", "Nierveentrombose"],
    "CORE-GU-044": ["Bloedstolsel in het pyelocaliceale systeem", "Urotheelcarcinoom"],
    "CORE-GU-045": ["Retroperitoneale fibrose", "Retroperitoneaal lymfoom"],
    "CORE-GU-046": ["Liposarcoom", "Lipoom", "Exofytisch renaal angiomyolipoom", "Teratoom"],
    "CORE-GU-048": ["Lymfoom", "Retroperitoneale fibrose", "Retroperitoneaal sarcoom"],
    "CORE-GU-050": ["Tuberculose", "Mycobacterium avium-complexinfectie", "Schimmelinfectie", "Necrotische lymfekliermetastasen", "Ziekte van Whipple"],
    "CORE-GU-051": ["Cystische degeneratie in een solide tumor", "Behandelingsgerelateerde tumornecrose", "Lymfangioom", "Cystisch teratoom"],
    "CORE-GU-052": ["Blande trombus", "Tumortrombus"],
    "CORE-GU-057": ["Lipiderijk bijnieradenoom", "Myelolipoom", "Bijnierbloeding"],
    "CORE-GU-063": ["Bijniermetastase", "Bijnieradenoom"],
    "CORE-GU-064": ["Endotheliale bijniercyste", "Bijnierpseudocyste", "Cystisch gedegenereerde bijniertumor"],
    "CORE-GU-067": ["Traumatische perinefrische collectie", "Postoperatieve collectie", "Perinefrisch abces"],
    "CORE-GU-069": ["Urotheelcarcinoom", "Bloedstolsel"],
    "CORE-GU-070": ["Blaassteen", "Bloedstolsel", "Urotheelcarcinoom"],
    "CORE-GU-072": ["Recente instrumentatie", "Enterovesicale fistel", "Emfysemateuze cystitis"],
    "CORE-GU-075": ["Bekkenorgaanprolaps", "Neuromusculaire aandoening", "Bindweefselziekte", "Inflammatoire darmziekte"],
    "CORE-GU-076": ["Urotheelcarcinoom", "Schistosomiasis", "Tuberculose", "Cyclofosfamidecystitis", "Radiatiecystitis"],
    "CORE-GU-080": ["Utriculuscyste", "Cyste van de ductus Müllerianus", "Cyste van de ductus ejaculatorius", "Cystische benigne prostaathyperplasie", "Prostaatabces"],
    "CORE-GU-087": ["Urethradivertikel", "Gartnergangcyste", "Bartholin-kliercyste", "Skene-kliercyste", "Naboth-cyste"],
    "CORE-GU-088": ["Urethradivertikel", "Skene-kliercyste", "Gartnergangcyste", "Bartholin-kliercyste"],
    "CORE-GU-092": ["Primaire testistumor", "Lymfoom", "Epidermoïdcyste", "Granulomateuze aandoening"],
    "CORE-GU-093": ["Kiemceltumor", "Lymfoom", "Sarcoïdose"],
    "CORE-GU-094": ["Epididymo-orchitis", "Testistorsie", "Torsie van een testisappendix"],
    "CORE-GU-097": ["Kiemceltumor", "Testiculair lymfoom"],
    "CORE-GU-098": ["Kiemceltumor", "Testiculair lymfoom", "Sarcoïdose"],
    "CORE-GU-099": ["Spermatocele", "Epididymiscyste"],
    "CORE-GU-100": ["Epididymo-orchitis", "Testistorsie"],
    "CORE-GU-101": ["Epididymo-orchitis", "Testistorsie", "Ingeklemde liesbreuk", "Cellulitis", "Gangreen van Fournier"],
    "CORE-GU-104": ["Endometriumhyperplasie", "Endometriumcarcinoom", "Endometriumpoliep", "Submuceus uterusmyoom"],
    "CORE-GU-105": ["Endometriumpoliep", "Endometriumhyperplasie", "Endometriumcarcinoom", "Submuceus uterusmyoom"],
    "CORE-GU-107": ["Hematometra", "Pyometra", "Hydrometra"],
    "CORE-GU-109": ["Endometriumpoliep", "Submuceus uterusmyoom", "Intra-uteriene synechieën"],
    "CORE-GU-110": ["Arcuaire uterus", "Septate uterus", "Bicornuate uterus", "Uterus didelphys"],
    "CORE-GU-112": ["Ovariumcyste", "Hydrosalpinx"],
    "CORE-GU-114": ["Endometriumhyperplasie", "Endometriumpoliep", "Endometriumcarcinoom", "Tamoxifengerelateerde verandering"],
    "CORE-GU-115": ["Zeer vroege intra-uteriene zwangerschap", "Anembryonale zwangerschap", "Pseudogestationele zak bij ectopische zwangerschap"],
    "CORE-GU-116": ["Arterioveneuze malformatie", "Veneuze obstructie", "Pelvien congestiesyndroom", "Asymptomatische anatomische variant"],
    "CORE-GU-119": ["Hemorragische ovariumcyste", "Maligne ovariumneoplasma"],
    "CORE-GU-120": [
        "Hemorragische ovariumcyste",
        "Endometrioom",
        "Dermoïdcyste",
        "Goedaardige of kwaadaardige ovariumtumor",
    ],
    "CORE-GU-122": ["Hemorragische ovariumcyste", "Endometrioom", "Hydrosalpinx", "Dermoïdcyste", "Ovariumcarcinoom"],
    "CORE-GU-124": ["Primair ovariumcarcinoom", "Ovariële metastasen", "Endometrioom"],
    "CORE-GU-126": ["Tubo-ovarieel abces", "Ovariumneoplasma", "Hemorragische ovariumcyste", "Endometrioom"],
    "CORE-GU-128": ["Ovariumtorsie", "Ovariumtumor", "Ovarieel hyperstimulatiesyndroom"],
}
CARDIAC_QUESTION_DEFAULT = "What is the abnormality on the images below?"
CARDIAC_QUESTION_DEFAULT_NL = "Wat is de afwijking op onderstaande beelden?"
MISSING_CLINICAL_HISTORY = {
    "",
    "none",
    "n/a",
    "na",
    "not available",
    "clinical information not available",
    "no clinical history",
}

HISTORY_OVERRIDES_NL = {
    "CORE-PED-047": "3-jarige met een urineweginfectie.",
    "CORE-PED-063": "Jongen van 8 dagen met persisterend vochtverlies uit de navel.",
    "CORE-PED-069": "17-jarige met een testiculaire massa.",
    "CORE-PED-070": "11-jarige met bekkenpijn.",
    "CORE-PED-093": "Zuigeling van zes maanden met een toenemende hoofdomtrek.",
    "CORE-PED-098": "A terme geboren zuigeling met een nekmassa.",
    "CORE-PED-145": "12-jarige patiënt met een Salter-Harris-IV-fractuur van de proximale tibia in de voorgeschiedenis.",
    "CORE-NR-032": "61-jarige vrouw na trauma van de linker ACI.",
    "CORE-NR-103": "Meisje van 5 maanden na een val van een bank.",
    "CORE-NR-147": "Eerder gezonde man na trauma met zwelling, pijn en duidelijke afname van de gezichtsscherpte.",
    "CORE-IR-030": "Incidentele bevinding op een preoperatieve CT-scan. Wat is het aangewezen beleid?",
    "CORE-IR-029": "63-jarige vrouw met naar de lever gemetastaseerd rectumcarcinoom en chemotherapieresistente ziekte. Op welke behandeling wordt deze patiënt voorbereid?",
    "CORE-IR-068": "Meisje van 2 maanden met rechtszijdige halszwelling. Wat zijn de behandelingsopties voor het getoonde letsel?",
    "CORE-IR-014": "Na beenmergtransplantatie, trombocytopenie en verhoogde leverfunctietests. De kathetermetingen tonen een drukstijging van 10 naar 24 mmHg; de rechteratriumdruk bedraagt 6-8 mmHg.",
    "CORE-IR-022": "60-jarige man met naar de longen gemetastaseerd coloncarcinoom, recent behandeld met pulmonale metastasectomie. Wat zijn de behandelingsopties?",
    "CORE-IR-028": "Koorts en leukocytose twee weken na embolisatie van de leverslagader. De beelden werden één en twee weken na embolisatie verkregen.",
    "CORE-IR-038": "Koorts en leukocytose één week na gastrectomie, gecompliceerd door een abces. Na verwijdering van de drainagekatheter werd de patiënt hypotensief en tachycard, waarna een CT werd verricht.",
    "CORE-IR-047": "Blaascarcinoom na cystectomie en aanleg van een ileumconduit, gecompliceerd door bilaterale uretero-enterische anastomosestricturen. Welke katheters zijn zichtbaar op de beelden?",
    "CORE-IR-070": "45-jarige vrouw na resectie van een craniofaryngioom, met een postoperatieve longembolie, verwezen voor plaatsing van een vena-cava-inferiorfilter. De beelden tonen twee verschillende patiënten. Wat is het verschil?",
    "CORE-IR-072": "60-jarige vrouw met een permanent aanwezige vena-cava-inferiorfilter, zes jaar eerder geplaatst, en chronische bilaterale beenzwelling met acute verergering sinds één week. Is een behandeling mogelijk?",
    "CORE-IR-096": "34-jarige man na een verkeersongeval met zwelling van de linkerdij. Een percutane drain bleef twee weken ter plaatse met aanhoudende seromelkachtige productie van 30-40 ml per dag. Het contrastonderzoek werd via de drain uitgevoerd. Wat zijn de behandelingsopties?",
    "CORE-IR-100": "36-jarige man met alcoholmisbruik en plotselinge hevige thoracale pijn. Na chirurgische behandeling heeft hij aanhoudende leukocytose en koorts. Beoordeel de meest recente beelden.",
    "CORE-GU-003": "60-jarige man met gewichtsverlies en flankpijn; na vier maanden werden follow-up-CT-beelden verkregen.",
    "CORE-GU-005": "23-jarige vrouw met acuut nierfalen en buikpijn; na drie maanden behandeling werd een follow-up-CT met contrast verkregen.",
    "CORE-GU-013": "56-jarige man na radiofrequente ablatie van een linkszijdig niercelcarcinoom; MR-beelden één en zes maanden na ablatie.",
    "CORE-GU-016": "40-jarige vrouw met plots ontstane koorts en flankpijn. Aanvullende beelden tonen bij een andere patiënt een tweede manifestatie van dezelfde ziekte.",
    "CORE-GU-051": "43-jarige vrouw en 50-jarige man met incidenteel ontdekte retroperitoneale laesies.",
    "CORE-GU-059": "Verkeersongeval; CT-beelden bij opname, na 24 uur en na twee weken.",
    "CORE-GU-066": "55-jarige vrouw met een eerdere cystectomie en acuut nierfalen; er werden een conduitogram en vervolgens een antegraad nefrostogram uitgevoerd.",
    "CORE-GU-067": "52-jarige man met hevige acute linkerflankpijn.",
    "CORE-GU-073": "Conventioneel cystogram en CT-cystogram van twee patiënten met hematurie na trauma.",
    "CORE-GU-080": "58-jarige man met diabetes, dysurie en perineale pijn; CT bij presentatie en follow-up-MRI na zeven dagen.",
    "CORE-GU-086": "65-jarige man met radiotherapie voor prostaatkanker in de voorgeschiedenis en 35-jarige man met een schotwond in het bekken in de voorgeschiedenis.",
    "CORE-GU-112": "MRI en echografie van twee patiënten met bekkenpijn.",
    "CORE-GU-114": "Echografie van het bekken en MR-beelden van twee patiënten met postmenopauzaal bloedverlies.",
    "CORE-MSK-129": "32-jarige vrouw met kniepijn na trauma.",
    "CORE-ER-025": "59-jarige vrouw na een val van de trap.",
    "CORE-ER-034": "34-jarige man na een frontale hoogenergetische autoaanrijding; tracheaal letsel op CT, bevestigd bij bronchoscopie.",
    "CORE-ER-035": "35-jarige man na een frontale autoaanrijding.",
    "CORE-ER-037": "41-jarige man na een frontale autoaanrijding met airbagactivatie en thoracale pijn.",
    "CORE-ER-043": "45-jarige man na stomp buiktrauma.",
    "CORE-ER-047": "78-jarige man na transurethrale resectie van de prostaat.",
    "CORE-ER-064": "40-jarige man na een val op een uitgestrekte hand.",
    "CORE-ER-069": "20-jarige man na een val van hoogte.",
    "CORE-ER-163": "10-jarig meisje na een val.",
    "CORE-BR-095": "58-jarige vrouw na excisiebiopsie van de linker borst in een extern centrum.",
}

DIAGNOSIS_OVERRIDES_NL = {
    "CORE-CH-012": "Atelectase van de rechter midden- en onderkwab door een centraal bronchogeen carcinoom",
    "CORE-CH-013": "Atelectase van de rechter bovenkwab met omgekeerd S-teken van Golden door een endobronchiale carcinoïdtumor",
    "CORE-CH-014": "Atelectase van de rechter middenkwab door een slijmprop",
    "CORE-CH-015": "Atelectase van de linker bovenkwab door een niet-kleincellig longcarcinoom",
    "CORE-CH-028": "Voorste mediastinale massa: diffuus grootcellig B-cellymfoom",
    "CORE-CH-030": "Maligne kiemceltumor: primaire mediastinale dooierzaktumor",
    "CORE-CH-037": "Achterste mediastinale massa: schwannoom",
    "CORE-CH-044": "Inflammatoire myofibroblastische tumor van het mediastinum",
    "CORE-CH-046": "Tracheatumor: adenoïdcystisch carcinoom",
    "CORE-CH-057": "Solitaire fibreuze tumor van de pleura",
    "CORE-CH-060": "Desmoïdtumor",
    "CORE-CH-065": "Pectus excavatum met pseudo-pneumonie van de rechter middenkwab",
    "CORE-CH-068": "Partieel abnormale pulmonale veneuze retour van de linker bovenkwab",
    "CORE-CH-074": "Schwannoom van de linker plexus brachialis",
    "CORE-CH-084": "Endobronchiale carcinoïdtumor",
    "CORE-CH-110": "Syndroom van immotiele cilia, of primaire ciliaire dyskinesie",
    "CORE-CH-121": "Pseudoaneurysma van de longslagader",
    "CORE-CH-125": "Pulmonale arteriële tumorembolieën",
    "CORE-CH-126": "Longslagadersarcoom",
    "CORE-NR-117": "Spinale zenuwschedetumor",
    "CORE-NR-123": "Spinaal epidermoïd",
    "CORE-NR-166": "Veneuze vasculaire malformatie van de aangezichtszenuw met ossificerend hemangioom van het slaapbeen",
    "CORE-NR-175": "Aberrante arteria carotis interna",
    "CORE-NR-178": "Meningeoom van de oogzenuwschede",
    "CORE-PED-003": "Dextrotranspositie van de grote arteriën",
    "CORE-PED-004": "Totale abnormale pulmonale veneuze retour",
    "CORE-PED-010": "Rechter aortaboog met aberrante linker arteria subclavia",
    "CORE-PED-044": "Malpositie van navelarterie- en navelvenekatheters",
    "CORE-PED-051": "Autosomaal recessieve polycysteuze nierziekte",
    "CORE-PED-063": "Patente urachus",
    "CORE-PED-093": "Benigne vergroting van de subarachnoïdale ruimten",
    "CORE-PED-145": "Posttraumatische fysebrug van de proximale tibia",
    "CORE-PED-149": "Ziekte van Blount",
    "CORE-IR-009": "Aneurysma van de rechter kransslagader",
    "CORE-IR-027": "Occlusie van de truncus coeliacus met retrograde flow via de arteria gastroduodenalis",
    "CORE-IR-032": "Embolisatie van de bronchiale arterie",
    "CORE-IR-038": "Drainage van een abdominaal abces, gecompliceerd door letsel van de arteria epigastrica inferior en een pseudoaneurysma",
    "CORE-IR-046": "Rechtszijdige uretero-iliacale arteriële fistel",
    "CORE-IR-049": "Routinematige transurethrale wissel van een ureterstent",
    "CORE-IR-056": "Getunnelde drainagekatheter voor recidiverende ascites",
    "CORE-IR-072": "Acute op chronische trombose van de vena cava inferior en beide iliofemoropopliteale veneuze assen onder een permanente vena-cavafilter",
    "CORE-IR-073": "Acute op chronische diepe veneuze trombose van het rechter been door lymfekliercompressie",
    "CORE-IR-078": "Traumatisch pseudoaneurysma van de arteria carotis",
    "CORE-IR-081": "Pseudoaneurysma van de arteria femoralis",
    "CORE-IR-088": "Thoracic-outletsyndroom met aneurysma van de arteria subclavia",
    "CORE-GI-023": "Gastro-intestinale stromale tumor",
    "CORE-GI-036": "Duodenale gastro-intestinale stromale tumor",
    "CORE-GI-048": "Lymfoom bij coeliakie",
    "CORE-GI-105": "Levercirrose met tumorale poortadertrombose",
    "CORE-GI-106": "Cavernomateuze transformatie van de poortader",
    "CORE-GI-129": "Benigne galwegstrictuur na cholecystectomie",
    "CORE-GI-138": "Solide pseudopapillaire neoplasie",
    "CORE-GI-142": "Niet-functionerende pancreatische neuro-endocriene tumor",
    "CORE-BMRI-007": "Benigne lipidenrijk bijnieradenoom",
    "CORE-BMRI-016": "Multiloculaire cystische massa, Bosniak III",
    "CORE-BMRI-019": "Eenvoudige bijniercyste",
    "CORE-BMRI-020": "Staartdarmcyste, of retrorectaal cystisch hamartoom",
    "CORE-BMRI-026": "Duodenale carcinoïdtumor",
    "CORE-BMRI-036": "Feochromocytoom van de linker bijnier",
    "CORE-BMRI-051": "IgG4-gerelateerde scleroserende ziekte met auto-immuunpancreatitis, cholangiopathie en nierletsels",
    "CORE-BMRI-054": "Goed gedifferentieerd neuro-endocrien carcinoom van het ileum",
    "CORE-BMRI-070": "Talrijke arterieel hyperenhancerende leverlaesies, vermoedelijk benigne",
    "CORE-BMRI-075": "Pseudostenose van de ductus hepaticus communis door een kruisende rechter leverslagader",
    "CORE-BMRI-078": "Intraperitoneale bloeding",
    "CORE-BMRI-090": "Carcinosarcoom van de uterus, of maligne gemengde mülleriaanse tumor",
    "CORE-BMRI-094": "Benigne mature cystische teratoom",
    "CORE-BMRI-095": "Gastro-intestinale stromale tumor van het duodenum",
    "CORE-BMRI-100": "Hilair cholangiocarcinoom, of Klatskintumor",
    "CORE-BMRI-105": "Intraductaal papillair mucineus neoplasma van het hoofdkanaal",
    "CORE-BMRI-120": "Susceptibiliteitsartefact van een chirurgische clip dat een massa nabootst",
    "CORE-BMRI-125": "Ectopisch miltweefsel, of een intrapancreatische accessoire milt, als pseudomassa van de pancreas",
    "CORE-BMRI-135": "Solide pseudopapillaire tumor van de pancreas",
    "CORE-BMRI-141": "Gladspiertumor met onzeker maligne potentieel",
    "CORE-MSK-037": "Reusceltumor van het distale femur",
    "CORE-MSK-057": "Reusceltumor van de peesschede",
    "CORE-MSK-060": "Desmoïdtumor: benigne laesie met een agressief aspect",
    "CORE-MSK-064": "Agressieve fibromatose, of desmoïdtumor",
    "CORE-MSK-030": "Maffucci-syndroom met multipele enchondromen en wekedelhemangiomen",
    "CORE-MSK-072": "Bacteriële spondylodiscitis L2-L3",
    "CORE-MSK-101": "Sequelae van anterieure schouderluxatie met Hill-Sachs- en Bankartletsel",
    "CORE-MSK-102": "Parsonage-Turner-syndroom, of acute idiopathische brachiale neuritis",
    "CORE-MSK-112": "Ruptuur van het scafolunaire ligament",
    "CORE-MSK-117": "Ganglioncyste met compressie van de nervus peroneus communis",
    "CORE-MSK-142": "Ischemie van de rechter femurkopepifyse bij vroege ziekte van Legg-Calvé-Perthes",
    "CORE-ER-018": "Jeffersonfractuur",
    "CORE-ER-025": "Cervicale flexie-traanfractuur",
    "CORE-ER-027": "Dissectie van de arteria vertebralis of arteria carotis",
    "CORE-ER-035": "Fladderthorax",
    "CORE-ER-037": "Hemopericard na stomp thoraxtrauma met myocardletsel",
    "CORE-ER-055": "Nierlaceratie met hematoom en actieve vasculaire extravasatie",
    "CORE-ER-064": "Galeazzi-fractuurluxatie",
    "CORE-ER-069": "Monteggia-fractuurluxatie",
    "CORE-ER-070": "Bekkenfractuur door anteroposterieure compressie",
    "CORE-ER-144": "Tubo-ovarieel abces bij pelviene inflammatoire ziekte",
    "CORE-ER-145": "Geruptureerd abdominaal aorta-aneurysma",
    "CORE-CARD-006": "Goedaardige anomalie van de linker arteria circumflexa",
    "CORE-CARD-007": "Goedaardige anomalie van de linker kransslagader",
    "CORE-CARD-008": "Anomalie van de linker kransslagader met een maligne verloop",
    "CORE-CARD-009": "Afwijkende oorsprong van de rechter kransslagader met een maligne verloop",
    "CORE-CARD-012": "Partieel abnormale pulmonale veneuze retour",
    "CORE-CARD-014": "Totale abnormale pulmonale veneuze retour",
    "CORE-CARD-016": "Aberrante rechter arteria subclavia",
    "CORE-CARD-027": "Longslagaderstenose",
    "CORE-CARD-036": "Afwezige longslagader",
    "CORE-CARD-045": "Calciumscore van de kransslagaders",
    "CORE-CARD-046": "Stenose van de rechter kransslagader",
    "CORE-CARD-048": "Aneurysma van de kransslagader",
    "CORE-CARD-077": "Longslagadersarcoom",
    "CORE-CARD-107": "Longslagaderkatheter",
    "CORE-CARD-111": "Doorgankelijke bypassgreffen van de kransslagaders",
    "CORE-BR-036": "Fyllodestumor",
    "CORE-BR-053": "Echografisch beeld van een extracapsulaire ruptuur van een siliconenimplantaat",
    "CORE-BR-070": "Bilaterale benigne ogende massa's",
    "CORE-BR-098": "Borstcarcinoom met invasie van de pectoralisspier",
}

ANSWER_DETAILS_OVERRIDES_NL = {
    "CORE-PED-063": (
        "Bevindingen\n"
        "De sagittale echografie van de voorste buikwand toont een tubulaire structuur die de blaaskoepel met de navel verbindt, passend bij een persisterende urachus.\n"
        "Differentiaaldiagnose\n"
        "Persisterende ductus omphalomesentericus: deze verbindt de navel met de dunne darm en kan zich presenteren met enterale afscheiding uit de navel.\n\n"
        "Urachussinus: deze loopt blind vanuit de navel en heeft geen open verbinding met de blaas.\n"
        "Kernpunten\n"
        "De urachus is een embryonale verbinding tussen de blaas en de navel die normaal oblitereert tot het ligamentum umbilicale medianum.\n\n"
        "Er bestaan vier belangrijke urachusafwijkingen: een patente urachus, urachussinus, urachusdivertikel en urachuscyste.\n\n"
        "Een patente urachus is aan beide uiteinden open en presenteert zich meestal in de neonatale periode met urineverlies uit de navel.\n\n"
        "Een patente urachus of urachusdivertikel kan samengaan met urethrale obstructie, zoals posterieure-urethrakleppen, urethra-atresie of het prune-bellysyndroom.\n\n"
        "Echografie in het sagittale vlak is het eerstekeuzeonderzoek; cystografie of fistulografie kan de open verbinding met de blaas bevestigen.\n\n"
        "Urachusresten kunnen geïnfecteerd raken; maligne ontaarding tot een urachuscarcinoom is een zeldzame late complicatie.\n"
        "Beleid\n"
        "Beoordeel eerst of er een onderliggende urinewegobstructie bestaat. Kleine asymptomatische urachusresten bij jonge zuigelingen kunnen aanvankelijk echografisch worden opgevolgd, maar een persisterende symptomatische patente urachus wordt chirurgisch geëxcideerd.\n"
        "Referenties\n"
        "1. Yu JS, Kim KW, Lee HJ, et al. Urachal remnant diseases: spectrum of CT and US findings. RadioGraphics. 2001;21(2):451-461.\n"
        "2. Galati V, Donovan B, Ramji F, et al. Management of urachal remnants in early childhood. J Urol. 2008;180(4 suppl):1824-1827."
    ),
    "CORE-PED-145": (
        "Bevindingen\n"
        "De coronale vetonderdrukte 3D-gradiëntecho-opname van de rechterknie toont onderbreking van de normale hyperintense proximale tibiale fysis door een hypointense benige brug, terwijl de distale femurfysis een normaal aspect heeft.\n"
        "Differentiaaldiagnose\n"
        "Acuut fyseletsel zonder brugvorming: hierbij is op T2-gewogen beelden een hyperintens signaal in de fysis zichtbaar, met omgevend wekedelenoedeem.\n"
        "Kernpunten\n"
        "Een groeistilstand door een fysebrug treedt op bij ongeveer 15% van de fysefracturen.\n\n"
        "De distale tibia is de frequentste locatie, gevolgd door het distale femur en de proximale tibia.\n\n"
        "Het risico op een groeistoornis neemt toe bij verplaatsing, comminutie en een fractuurlijn die loodrecht op de fysis staat.\n\n"
        "Jonge patiënten en letsels van het distale femur of de proximale tibia hebben door de resterende groei een groter risico op standsafwijkingen en beenlengteverschil.\n\n"
        "Op radiografie kan aanvankelijk vernauwing of verbreding van de fysis zichtbaar zijn; later ontstaan een benige brug, angulaire deformiteit of beenlengteverschil.\n\n"
        "MRI detecteert een beginnende fysebrug eerder dan radiografie; driedimensionale vetonderdrukte gradiëntecho-opnamen maken kartering van de fysebrug mogelijk voor de operatieve planning.\n"
        "Beleid\n"
        "Bij voldoende resterende groei kan een fysebrug die minder dan 50% van het oppervlak van de fysis beslaat, worden gereseceerd. Bij een grotere brug kunnen een corrigerende osteotomie en/of contralaterale epifysiodese nodig zijn om verdere deformiteit of beenlengteverschil te beperken.\n"
        "Referenties\n"
        "1. Lohman M, Kivisaari A, Vehmas T, et al. MRI in the assessment of growth arrest. Pediatr Radiol. 2002;32(1):41-45.\n"
        "2. Ecklund K, Jaramillo D. Imaging of growth disturbance in children. Radiol Clin North Am. 2001;39(4):823-841."
    ),
}

FIGURE_WORD = r"(?:fig(?:uren|ures|uur|ure|s)?|afb(?:eeldingen|eelding)?)\.?"
FIGURE_LABEL = r"(?:\d+(?:[.,]\d+)?[a-z]?|(?-i:[A-Z]))\b"
FIGURE_REFERENCE = re.compile(
    rf"\(?\b{FIGURE_WORD}\s*{FIGURE_LABEL}"
    r"(?:\s*(?:,|&|and|en|to|tot|[-–])\s*"
    rf"(?:{FIGURE_WORD})?\s*{FIGURE_LABEL})*\s*\)?",
    re.IGNORECASE,
)
FIGURE_PARENTHETICAL = re.compile(
    rf"\([^()]*\b{FIGURE_WORD}\s*{FIGURE_LABEL}"
    r"(?:\s*(?:,|&|and|en|to|tot|[-–])\s*"
    rf"(?:{FIGURE_WORD})?\s*{FIGURE_LABEL})*[^()]*\)",
    re.IGNORECASE,
)
NUMERIC_FIGURE_LABEL = r"\d{1,3}[.,]\d{1,3}[a-z]?"
FIGURE_POINTER = r"(?:arrow|arrows|pijl|pijlen|asterisk)"
ORPHAN_FIGURE_PARENTHETICAL = re.compile(
    rf"\(\s*(?:{FIGURE_POINTER}\s+(?:in\s+)?)?"
    rf"{NUMERIC_FIGURE_LABEL}(?:\s+{FIGURE_POINTER})?"
    rf"(?:\s*(?:,\s*(?:(?:and|en)\s+)?|(?:and|en)\s+)"
    rf"(?:{FIGURE_POINTER}\s+(?:in\s+)?)?"
    rf"{NUMERIC_FIGURE_LABEL}(?:\s+{FIGURE_POINTER})?)*\s*\)",
    re.IGNORECASE,
)
DANGLING_FIGURE_SUFFIX = re.compile(
    rf",?\s*(?:and|en)\s+{NUMERIC_FIGURE_LABEL}"
    rf"(?:\s+{FIGURE_POINTER})?\s*\)",
    re.IGNORECASE,
)


def _section_key(line):
    for key, pattern in ANSWER_SECTION_HEADINGS.items():
        if pattern.match(line):
            return key
    return None


def _clean_extracted_text(value):
    value = re.sub(
        r"\b([A-Za-z]*(?:fi|fl|ff))\s+(?=[a-z])",
        r"\1",
        value,
    )
    return value.replace("oft en", "often").replace("aft er", "after")


def _strip_figure_references(value):
    value = FIGURE_PARENTHETICAL.sub("", value)
    value = FIGURE_REFERENCE.sub("", value)
    value = ORPHAN_FIGURE_PARENTHETICAL.sub("", value)
    value = DANGLING_FIGURE_SUFFIX.sub("", value)
    value = re.sub(r"\(\s*\)", "", value)
    value = re.sub(r"\s+([,.;:])", r"\1", value)
    value = re.sub(r"^[\s,.;:–-]+", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _capitalize_initial(value):
    value = (value or "").strip()
    for index, character in enumerate(value):
        if character.isalpha():
            return value[:index] + character.upper() + value[index + 1:]
    return value


_DUTCH_TEXT_REPLACEMENTS = (
    (r"(?m)^Findings$", "Bevindingen"),
    (r"(?m)^Differential Diagnosis$", "Differentiaaldiagnose"),
    (r"(?m)^Teaching Points$", "Kernpunten"),
    (r"(?m)^Management$", "Beleid"),
    (r"(?m)^Further Readings?$", "Referenties"),
    (r"\bTrue Disease Extent Demonstrated on MR Imaging\b", "werkelijke ziekte-uitbreiding aangetoond met MRI"),
    (r"\b(?:niet-contrast|noncontrast|onverbeterde) (?:berekende |gecomputeerde )?tomografie\s*\(CT\)", "CT zonder contrast"),
    (r"\b(?:niet-contrast|noncontrast|onverbeterde) CT\b", "CT zonder contrast"),
    (r"\bsingle[- ](?:photon|foton)[- ]?emissie (?:berekende|gecomputeerde) tomografie\b", "SPECT"),
    (r"\bcontrast[- ]versterkte\b", "contrastversterkte"),
    (r"\bcontrast[- ]versterkt\b", "contrastversterkt"),
    (r"\bcross[- ]sectionele imaging\b", "doorsnedebeeldvorming"),
    (r"\bcross[- ]sectional imaging\b", "doorsnedebeeldvorming"),
    (r"\bplain film\b", "conventionele radiografie"),
    (r"\bgecomputeerde tomografie\b", "computertomografie"),
    (r"\bberekende tomografie\b", "computertomografie"),
    (r"\bberekend tomografie\b", "computertomografie"),
    (r"\bonverbeterde\b", "ongecontrasteerde"),
    (r"\bultrageluid[- ]geleide\b", "echogeleide"),
    (r"\bultrasound[- ]guided\b", "echogeleide"),
    (r"\bultrageluid\b", "echografie"),
    (r"\bultrasound\b", "echografie"),
    (r"\bimaging findings\b", "beeldvormingsbevindingen"),
    (r"\bbeeldvorming-bevindingen\b", "beeldvormingsbevindingen"),
    (r"\bCT findings\b", "CT-bevindingen"),
    (r"\bMR imaging\b", "MRI"),
    (r"\bfluid attenuation\b", "vloeistofattenuatie"),
    (r"\bfluid verzachting\b", "vloeistofattenuatie"),
    (r"\bfluid demping\b", "vloeistofattenuatie"),
    (r"\bfluid[- ]fill(?:ed)?\b", "vloeistofgevuld"),
    (r"\blucht-fluid niveaus?\b", "lucht-vloeistofniveau"),
    (r"\bconservative management\b", "conservatieve behandeling"),
    (r"\bmanagement\b", "beleid"),
    (r"\bworkup\b", "diagnostische evaluatie"),
    (r"\bfill-in\b", "opvulling"),
    (r"\bup to\b", "tot"),
    (r"\bfindings\b", "bevindingen"),
    (r"\bfinding\b", "bevinding"),
    (r"\bimaging\b", "beeldvorming"),
    (r"\bfluid\b", "vloeistof"),
    (r"\bpresent\b", "aanwezig"),
    (r"\bnonspecific\b", "niet-specifiek"),
    (r"\bspecific\b", "specifiek"),
    (r"\bfixed\b", "vast"),
    (r"\bcontrast fills\b", "contrastmiddel vult"),
    (r"\bTumor\b", "tumor"),
    (r"\bholge\b", "holle"),
    (r"\baftrekken angiogram\b", "subtractieangiogram"),
    (r"\bbehoefte aspiratie\b", "naaldaspiratie"),
    (r"\bcutoffvan\b", "onderbreking van"),
    (r"\bHeterogenely\b", "heterogeen"),
    (r"\bsirty-shadowing\b", "vuileschaduwartefact"),
    (r"\bubareolaire\b", "subareolaire"),
    (r"\bmammografief\b", "mammografisch"),
    (r"\blumbometrie\b", "lumpectomie"),
    (r"\bHet icoken van\b", "Verdikking van"),
    (r"\bBeeldvorming of growth disturbance in children\b", "Imaging of growth disturbance in children"),
)


def _polish_dutch_text(value):
    text = value or ""
    for pattern, replacement in _DUTCH_TEXT_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _cap_learning_points(chunks, maximum):
    if len(chunks) <= maximum:
        return chunks
    group_size = (len(chunks) + maximum - 1) // maximum
    return [
        " ".join(chunks[index:index + group_size]).strip()
        for index in range(0, len(chunks), group_size)
    ][:maximum]


def _split_learning_points(section_key, lines):
    if section_key == "references":
        # References are line-based citations. Splitting on every number-dot
        # sequence breaks page ranges such as "1473-1505." into fake items.
        chunks = []
        reference_start = re.compile(
            r"^(?:\d{1,2}\.\s+|[A-Z][A-Za-z'’-]+\s+[A-Z]{1,4}[.,])"
        )
        for raw_line in lines:
            line = _clean_extracted_text(raw_line.strip())
            if not line:
                continue
            if re.match(r"^Case\s+\d+\b", line, re.IGNORECASE):
                break
            if not chunks or reference_start.match(line):
                chunks.append(line)
            else:
                chunks[-1] = f"{chunks[-1]} {line}".strip()
    elif section_key == "differential":
        # Differential diagnoses are already line-based in the source data.
        # Keep each line separate instead of joining names into one paragraph.
        chunks = []
        for raw_line in lines:
            for part in re.split(r"\s*■\s*", raw_line.strip()):
                line = _strip_figure_references(
                    _clean_extracted_text(part.strip())
                )
                if line:
                    chunks.append(line)
    else:
        text = " ".join(line.strip() for line in lines if line.strip())
        text = re.sub(r"\s+", " ", text).strip()
        text = _strip_figure_references(_clean_extracted_text(text))
        if not text:
            return []
        chunks = re.split(r"(?<=[.!?])\s+(?=[A-Za-zÀ-ÖØ-öø-ÿ0-9])", text)

    if section_key == "teaching":
        chunks = _cap_learning_points(chunks, 6)

    items = []
    for chunk in chunks:
        chunk = _capitalize_initial(chunk.strip())
        if not chunk:
            continue
        if re.fullmatch(
            r"\d+(?:[.,]\d+)?[a-z]?(?:\s*,\s*\d+(?:[.,]\d+)?[a-z]?)*\)?[.!]?",
            chunk,
            re.IGNORECASE,
        ):
            continue
        lead = ""
        body = chunk
        if section_key == "references":
            match = re.match(r"^(\d+\.)\s*(.*)$", chunk)
            if match:
                lead, body = match.groups()
        else:
            match = re.match(r"^([^:]{1,75}):\s*(.+)$", chunk)
            if match:
                lead, body = match.groups()
        item = {"lead": lead, "text": body}
        if section_key == "differential" and lead:
            item["radiopaedia_url"] = (
                f"https://radiopaedia.org/search?q={quote_plus(lead)}"
            )
        items.append(item)
    return items


def parse_answer_details(value):
    sections = []
    current_key = None
    current_lines = []

    def append_current():
        if not current_key:
            return
        items = _split_learning_points(current_key, current_lines)
        if items:
            sections.append({
                "key": current_key,
                "label": ANSWER_SECTION_LABELS[current_key],
                "items": items,
            })

    for raw_line in (value or "").splitlines():
        line = raw_line.strip()
        next_key = _section_key(line)
        if next_key:
            append_current()
            current_key = next_key
            current_lines = []
        elif current_key:
            current_lines.append(line)
    append_current()
    return sections


def _compact_gu_differential(card_id, correct_diagnosis):
    has_override = card_id in GU_DIFFERENTIAL_OVERRIDES_NL
    candidates = list(GU_DIFFERENTIAL_OVERRIDES_NL.get(card_id, []))

    cleaned = []
    for candidate in candidates:
        candidate = re.sub(
            r"^(?:zoals|waaronder)\s+",
            "",
            candidate.strip(" .;:"),
            flags=re.IGNORECASE,
        )
        candidate = _capitalize_initial(candidate)
        if not candidate or len(candidate) > 120:
            continue
        normalized = re.sub(r"\W+", "", candidate.lower())
        if normalized and all(
            normalized != re.sub(r"\W+", "", existing.lower())
            for existing in cleaned
        ):
            cleaned.append(candidate)

    if not cleaned:
        cleaned = [_capitalize_initial(correct_diagnosis)]
    elif not has_override and not any(
        re.sub(r"\W+", "", correct_diagnosis.lower())
        in re.sub(r"\W+", "", candidate.lower())
        or re.sub(r"\W+", "", candidate.lower())
        in re.sub(r"\W+", "", correct_diagnosis.lower())
        for candidate in cleaned
    ):
        cleaned.insert(0, _capitalize_initial(correct_diagnosis))

    return [{
        "lead": "",
        "text": candidate,
        "radiopaedia_url": f"https://radiopaedia.org/search?q={quote_plus(candidate)}",
    } for candidate in cleaned[:6]]


def _compact_gu_differential_section(
    card_id,
    sections,
    correct_diagnosis,
):
    compact_items = _compact_gu_differential(
        card_id,
        correct_diagnosis,
    )
    updated = []
    replaced = False
    for section in sections:
        if section["key"] == "differential":
            updated.append({**section, "items": compact_items})
            replaced = True
        else:
            updated.append(section)
    if not replaced:
        updated.insert(1 if updated else 0, {
            "key": "differential",
            "label": ANSWER_SECTION_LABELS["differential"],
            "items": compact_items,
        })
    return updated


@lru_cache(maxsize=None)
def load_core_translations(section_key, language):
    data_path = DATA_DIRECTORY / f"core_{section_key}_{language}.json"
    if not data_path.exists():
        return {}
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    return payload


@lru_cache(maxsize=None)
def load_core_section(section_key):
    data_path = DATA_DIRECTORY / f"core_{section_key}.json"
    if not data_path.exists():
        return []
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    dutch_translations = load_core_translations(section_key, "nl")
    dutch_histories = dutch_translations.get("histories", {})
    dutch_diagnoses = dutch_translations.get("diagnoses", {})
    dutch_answer_details = dutch_translations.get("answer_details", {})
    cards = []
    for card in payload.get("cards", []):
        diagnosis = _capitalize_initial(
            card.get("diagnosis") or "Diagnosis unavailable"
        )
        diagnosis_nl = _capitalize_initial(
            _polish_dutch_text(_clean_extracted_text(
                DIAGNOSIS_OVERRIDES_NL.get(
                    card["id"],
                    dutch_diagnoses.get(card["id"], diagnosis),
                )
            ))
        )
        answer_details = card.get("answer_details") or ""
        answer_details_nl = _polish_dutch_text(
            _clean_extracted_text(
                ANSWER_DETAILS_OVERRIDES_NL.get(
                    card["id"],
                    dutch_answer_details.get(card["id"], answer_details),
                )
            )
        )
        source_history = (card.get("history") or "").strip()
        cardiac_history_missing = (
            section_key == "cardiac"
            and source_history.lower() in MISSING_CLINICAL_HISTORY
        )
        history = (
            CARDIAC_QUESTION_DEFAULT
            if cardiac_history_missing
            else source_history or "Review the imaging case and formulate the diagnosis."
        )
        history_nl = _polish_dutch_text(
            _clean_extracted_text(
                CARDIAC_QUESTION_DEFAULT_NL
                if cardiac_history_missing
                else HISTORY_OVERRIDES_NL.get(
                    card["id"],
                    dutch_histories.get(card["id"], history),
                )
            )
        )
        answer_sections_nl = parse_answer_details(answer_details_nl)
        if section_key == "genitourinary":
            answer_sections_nl = _compact_gu_differential_section(
                card["id"],
                answer_sections_nl,
                diagnosis_nl,
            )
        question_images = card.get("question_images") or (
            [card["question_image"]] if card.get("question_image") else []
        )
        answer_images = card.get("answer_images") or (
            [card["answer_image"]] if card.get("answer_image") else []
        )
        cards.append({
            "ID": card["id"],
            "Category": "CORE Radiology",
            "Vraag": history,
            "Vraag_nl": history_nl,
            "Correct": [diagnosis],
            "Correct_nl": [
                diagnosis_nl
            ],
            "A": "",
            "B": "",
            "C": "",
            "D": "",
            "image_url": (
                f"/static/core/{section_key}/{question_images[0]}"
                if question_images else None
            ),
            "image_urls": [
                f"/static/core/{section_key}/{filename}"
                for filename in question_images
            ],
            "answer_image_url": (
                f"/static/core/{section_key}/{answer_images[0]}"
                if answer_images else None
            ),
            "answer_image_urls": [
                f"/static/core/{section_key}/{filename}"
                for filename in answer_images
            ],
            "answer_details": answer_details,
            "answer_sections": parse_answer_details(answer_details),
            "answer_details_nl": answer_details_nl,
            "answer_sections_nl": answer_sections_nl,
            "radiopaedia_url": f"https://radiopaedia.org/search?q={quote_plus(diagnosis)}",
            "case_label": card.get("label") or card["id"],
            "core_section": section_key,
            "question_key": f"core:{section_key}:{card['id']}",
        })
    return cards


def get_core_sections():
    sections = []
    for section in CORE_SECTIONS:
        count = len(load_core_section(section["key"]))
        if section.get("is_beta_demo"):
            count = section.get("placeholder_count", 1)
        sections.append({
            **section,
            "count": count,
            "display_count": count or section.get("placeholder_count", 0),
            "is_placeholder": count == 0,
        })
    return sections


def get_core_section(section_key):
    return next(
        (section for section in get_core_sections() if section["key"] == section_key),
        None,
    )
