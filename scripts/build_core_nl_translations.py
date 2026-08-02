import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from argostranslate import translate


ROOT = Path(__file__).resolve().parents[1]
PEDIATRIC_DIAGNOSIS_OVERRIDES_NL = json.loads(
    (ROOT / "data" / "core_pediatric_diagnosis_overrides_nl.json").read_text(
        encoding="utf-8"
    )
)
SECTION_HEADINGS = {
    "Findings": "findings",
    "Differential Diagnosis": "differential",
    "Teaching Points": "teaching",
    "Management": "management",
    "Further Reading": "references",
    "Further Readings": "references",
}
SECTION_HEADINGS_NL = {
    "findings": "Bevindingen",
    "differential": "Differentiaaldiagnose",
    "teaching": "Kernpunten",
    "management": "Beleid",
    "references": "Referenties",
}
MANUAL_HISTORY_TRANSLATIONS = {
    "CORE-CH-068": "49-jarige man met een nieuwe katheter in de linker vena jugularis interna. Er wordt een thoraxradiografie gemaakt om de positie te controleren; daarnaast is een eerdere CT-thorax beschikbaar.",
    "CORE-CH-069": "35-jarige man met ongecontroleerde hypertensie bij wie beeldvorming wordt verricht.",
    "CORE-IR-007": "59-jarige rookster met hoest. Een thoraxradiografie toont een nodus in de rechter onderkwab die persisteert na antibioticatherapie. Er wordt een biopsie verricht; tijdens de nazorg ontwikkelt de patiënt kortademigheid.",
    "CORE-IR-008": "74-jarige man, status na resectie van een niet-kleincellig longcarcinoom in de linker bovenkwab, met een nieuwe anteroposteriore vensterlymfeklier op CT waarvoor biopsie nodig is. Is er een toegangsweg tot deze laesie waarbij het longparenchym wordt gespaard?",
    "CORE-IR-010": "Bij de stadiëring van een recent gediagnosticeerd mammacarcinoom toont PET één solitaire PET-positieve laesie. Er wordt een biopsie gevraagd.",
    "CORE-IR-011": "Twee verschillende patiënten met longkanker, status na resectie van de contralaterale long, verwezen voor biopsie van bijniermassa's. Hoe minimaliseert u het risico op een pneumothorax in de resterende solitaire long?",
    "CORE-IR-014": "Na beenmergtransplantatie, trombocytopenie en verhoogde leverfunctietests. De druk gemeten met de katheter was 10 mmHg in figuur 14.1 en 24 mmHg in figuur 14.2. De rechteratriumdruk was 6-8 mmHg.",
    "CORE-IR-015": "76-jarige man met hematurie en pijn, drie dagen na een niet-doelgerichte nierbiopsie. Wat zijn de waarschijnlijkste diagnose en het aangewezen beleid?",
    "CORE-IR-020": "69-jarige vrouw met hepatocellulair carcinoom. Na meerdere embolisaties is er anterieur in segment VIII nog een groeiende vitale tumorhaard aanwezig. Welke procedure wordt uitgevoerd?",
    "CORE-IR-022": "60-jarige man met gemetastaseerd coloncarcinoom, recent status na pulmonale metastasectomie, verwezen met de PET/CT-scans in figuren 22.1 en 22.2. Wat zijn de behandelingsopties voor deze patiënt?",
    "CORE-IR-024": "68-jarige man met gemetastaseerd longcarcinoom en heuppijn.",
    "CORE-IR-026": "67-jarige man met longcarcinoom en één biopsiebewezen bijniermetastase. Vanwege cardiopulmonale comorbiditeit komt hij niet in aanmerking voor chirurgie. Tijdens de afgebeelde behandeling stijgt zijn bloeddruk plots van 125/65 naar 200/120 mmHg.",
    "CORE-IR-028": "Koorts en leukocytose twee weken na embolisatie van de arteria hepatica. Figuur 28.3 is één week na embolisatie; figuur 28.4 twee weken erna.",
    "CORE-IR-031": "Niercelcarcinoom, status na een val.",
    "CORE-IR-038": "Koorts en leukocytose één week na gastrectomie, gecompliceerd door een abces. Na verwijdering van de draineringskatheter werd de patiënt hypotensief en tachycard, waarna een CT werd verricht (figuur 38.3).",
    "CORE-IR-047": "Blaascarcinoom, status na cystectomie en ileumconduit, gecompliceerd door bilaterale uretero-enterische anastomosestricturen. Welke katheters zijn zichtbaar in figuur 47.3?",
    "CORE-IR-048": "68-jarige vrouw met ovariumcarcinoom en ureterobstructie. Beide nefrostomiekatheters zijn twee weken afgedopt zonder pijn, koorts of stijging van het serumcreatinine. Wat is de beste manier om de externe katheters te verwijderen?",
    "CORE-IR-051": "65-jarige vrouw met cervixcarcinoom, status na radiotherapie, met lekkage van urine uit het rectum.",
    "CORE-IR-053": "Slokdarmcarcinoom, status na gastric pull-up, met een proximale dunnedarmobstructie. Toegang voor enterale voeding is noodzakelijk.",
    "CORE-IR-054": "Ovariumcarcinoom met maligne obstructie van het colon. De laatste afbeelding werd vijf dagen na de getoonde procedure gemaakt.",
    "CORE-IR-058": "Resectie van een caverneus leverhemangioom, gecompliceerd door een intrahepatisch abces, koorts en leukocytose. Na drainage blijft er gal via de katheter aflopen. Wat is de volgende stap in het beleid?",
    "CORE-IR-059": "Cholangiocarcinoom met therapieresistente pruritus. Wat is op basis van het cholangiogram de optimale behandelingsstrategie?",
    "CORE-IR-061": "Coloncarcinoom, status na plaatsing van een biliaire wandstent vier maanden geleden, presenteert zich met koorts en leukocytose.",
    "CORE-IR-062": "72-jarige man met toenemende zwaarte en pijn in het rechterbeen. De klinische bevindingen en echografie zijn weergegeven.",
    "CORE-IR-065": "45-jarige vrouw met ongecontroleerde hypertensie. Op CT is een rechter bijniernodus zichtbaar met een densiteit van -7 HU. Wat wordt hier aangetoond?",
    "CORE-IR-066": "45-jarige man met biopsiebewezen kleincellig carcinoom in de rechter hemithorax, met acute kortademigheid en zwelling van het gelaat.",
    "CORE-IR-070": "45-jarige vrouw, recent status na resectie van een craniopharyngeoom, met een postoperatieve longembolie, verwezen voor plaatsing van een vena-cava-inferiorfilter. Figuren 70.1 en 70.2 tonen twee verschillende patiënten. Wat is het verschil?",
    "CORE-IR-071": "Therapieresistente buikpijn, status na plaatsing van een vena-cava-inferiorfilter.",
    "CORE-IR-072": "60-jarige vrouw met een permanent aanwezige vena-cava-inferiorfilter, zes jaar eerder geplaatst, met een voorgeschiedenis van enkele maanden met chronische bilaterale zwelling van de benen en één week acute verergering. Is er op basis van figuren 72.1-72.5 een mogelijke behandeling?",
    "CORE-IR-073": "74-jarige man met lymfoom en acute zwelling van de onderste ledematen. De CT en daaropvolgende interventie zijn weergegeven, gevolgd door controlebeelden. Welke aanvullende behandeling is mogelijk?",
    "CORE-IR-075": "50-jarige man met intracraniële metastase en een acute diepe veneuze trombose van het been, verwezen voor plaatsing van een vena-cava-inferiorfilter.",
    "CORE-IR-076": "Een eerste patiënt presenteert zich op de spoedgevallendienst met acute rugpijn. Welke belangrijke CT-bevindingen moeten worden herkend? Een tweede patiënt heeft acutere symptomen waarvoor endovasculaire en vervolgens chirurgische behandeling nodig is. Welke procedure wordt uitgevoerd?",
    "CORE-IR-077": "84-jarige man met hypertensie en diabetes, status na endovasculaire reparatie van een infrarenaal abdominaal aorta-aneurysma van 6 cm, drie jaar geleden.",
    "CORE-IR-078": "25-jarige man, per ambulance binnengebracht met een schotwond in het gelaat. De initiële CT en het arteriogram zijn weergegeven. Wat zijn de behandelingsopties?",
    "CORE-IR-079": "50-jarige vrouw na een verkeersongeval met hoge snelheid.",
    "CORE-IR-080": "50-jarige man met persisterende hypertensie ondanks behandeling met drie antihypertensiva.",
    "CORE-IR-086": "31-jarige Aziatische vrouw met de ziekte van Crohn en sikkelceltrait, eerder meermaals opgenomen wegens thoracale pijn en myalgie. Eerdere CT-onderzoeken van de thorax waren negatief. Nu presenteert zij zich met acute thoracale pijn en nieuwe beeldvormingsbevindingen ten opzichte van zes maanden eerder. Zij werd in het verleden langdurig met corticosteroïden behandeld.",
    "CORE-IR-087": "69-jarige man met diabetes en atherosclerose, met claudicatio ter hoogte van de bovenbenen en billen.",
    "CORE-IR-095": "87-jarige man met diabetes en blaascarcinoom, met koorts en bekkenpijn. Waar bevindt het abces zich en wat is de meest geschikte toegangsweg voor aspiratie?",
    "CORE-IR-096": "34-jarige man, status na een verkeersongeval, met zwelling van de linkerdij. In de collectie op figuur 96.1 werd percutaan een drain geplaatst. Deze bleef twee weken ter plaatse met een aanhoudende seromelkachtige productie van 30-40 cc per dag. Figuur 96.2 toont een contrastonderzoek via de aanwezige drain. Wat zijn de behandelingsopties?",
    "CORE-IR-099": "67-jarige man, twee weken status na distale oesofagectomie en gedeeltelijke gastrectomie, met nieuwe koorts en leukocytose. De volgende onderzoeken werden verricht.",
    "CORE-IR-101": "56-jarige man met lymfoom, gestuwde halsvenen, hypotensie en tachycardie. Wat zijn de behandelingsopties?",
    "CORE-PED-078": "Premature baby van 28 weken, één week oud.",
    "CORE-PED-081": "Premature jongen van 28 weken, één week oud (eerste afbeelding). De tweede afbeelding is acht weken later gemaakt.",
    "CORE-PED-082": "6-jarige met hoofdpijn en een veranderde mentale toestand.",
    "CORE-PED-063": "Jongen van 8 dagen met persisterend vochtverlies uit de navel.",
    "CORE-PED-086": "2-jarige met een ontwikkelingsachterstand.",
    "CORE-PED-133": "Jongen van 13 maanden met verkorting en een standsafwijking van het linker been.",
    "CORE-PED-145": "12-jarige patiënt met een Salter-Harris-IV-fractuur van de proximale tibia in de voorgeschiedenis.",
}
MANUAL_DIAGNOSIS_TRANSLATIONS = {
    "CORE-PED-063": "Patente urachus",
    "CORE-PED-086": "Dandy-Walkermalformatie",
    "CORE-PED-133": "Proximale focale femurdeficiëntie (PFFD)",
    "CORE-PED-145": "Posttraumatische fysebrug van de proximale tibia",
}
MANUAL_DIAGNOSIS_TRANSLATIONS.update(PEDIATRIC_DIAGNOSIS_OVERRIDES_NL)
MANUAL_ANSWER_TRANSLATIONS = {
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
    "CORE-PED-086": (
        "Bevindingen\n"
        "De axiale en sagittale MR-beelden tonen een vergrote achterste schedelgroeve met een grote liquorhoudende ruimte die vrij communiceert met de vierde ventrikel. Het tentorium staat hoog, de cerebellaire hemisferen zijn uit elkaar gedrongen en de cerebellaire vermis is hypoplastisch en craniaal geroteerd.\n"
        "Differentiaaldiagnose\n"
        "Blake-pouchcyste: cystische verwijding vanuit de vierde ventrikel met een intacte of slechts craniaal geroteerde vermis, zonder uitgesproken vergroting van de achterste schedelgroeve.\n\n"
        "Mega cisterna magna: vergrote retrocerebellaire liquorruimte met een normale vermis en vierde ventrikel, zonder relevant massa-effect.\n\n"
        "Arachnoïdale cyste van de achterste schedelgroeve: extra-axiale liquorcollectie zonder communicatie met de vierde ventrikel, met massa-effect op een normaal aangelegde vermis.\n"
        "Kernpunten\n"
        "De Dandy-Walkermalformatie wordt gekenmerkt door cystische dilatatie van de vierde ventrikel, hypoplasie en craniële rotatie van de vermis en vergroting van de achterste schedelgroeve met elevatie van het tentorium.\n\n"
        "De verouderde term 'Dandy-Walkervariant' wordt beter vermeden omdat hij verschillende afwijkingen zonder uniforme diagnostische criteria groepeert.\n\n"
        "Hydrocefalus komt frequent voor en kan bij presentatie verantwoordelijk zijn voor een toenemende hoofdomtrek, braken of tekenen van verhoogde intracraniële druk.\n\n"
        "Geassocieerde supratentoriële afwijkingen omvatten onder meer dysgenesie van het corpus callosum, heterotopieën van grijze stof, corticale ontwikkelingsstoornissen, holoprosencefalie en encefaloceles.\n\n"
        "De neurologische prognose wordt vooral bepaald door de ernst van de vermishypoplasie, bijkomende hersenafwijkingen en de mate waarin hydrocefalus onder controle kan worden gebracht.\n\n"
        "MRI, met name de midsagittale opname, is de beste techniek om de vermis, de communicatie met de vierde ventrikel en bijkomende intracraniële afwijkingen te beoordelen.\n"
        "Beleid\n"
        "Beoordeel systematisch de aanwezigheid en ernst van hydrocefalus en zoek naar geassocieerde supra- en infratentoriële afwijkingen. Symptomatische hydrocefalus vereist neurochirurgische behandeling, afgestemd op de liquordynamiek, bijvoorbeeld met een ventriculoperitoneale of cystoperitoneale shunt of een endoscopische derde ventriculostomie.\n"
        "Referenties\n"
        "1. Patel S, Barkovich AJ. Analysis and classification of cerebellar malformations. AJNR Am J Neuroradiol. 2002;23(7):1074-1087.\n"
        "2. Barkovich AJ, Kjos BO, Norman D, Edwards MS. Revised classification of posterior fossa cysts and cystlike malformations based on the results of multiplanar MR imaging. AJR Am J Roentgenol. 1989;153(6):1289-1300."
    ),
    "CORE-PED-133": (
        "Bevindingen\n"
        "Het scanogram toont een uitgesproken verkorting van het linker femur. De epifyse van de femurkop lijkt los te staan van de femurhals doordat de tussenliggende kraakbenige verbinding nog niet is verbeend en daarom niet zichtbaar is op de radiografie.\n\n"
        "Het linker acetabulum is ondiep en dysplastisch.\n"
        "Differentiaaldiagnose\n"
        "Geïsoleerde congenitale verkorting van het femur: hierbij is het femur verkort, maar blijven de proximale femurkop-halsverbinding en de heupstabiliteit relatief goed behouden.\n\n"
        "Femur-fibula-ulnasyndroom: hierbij gaat de femurafwijking samen met fibulaire en ulnaire reductiedefecten.\n"
        "Kernpunten\n"
        "Proximale focale femurdeficiëntie is een spectrum van congenitale afwijkingen, variërend van geringe femurverkorting tot ernstige proximale femurdeficiëntie met acetabulaire dysplasie.\n\n"
        "De aandoening is meestal sporadisch en unilateraal; ipsilaterale fibulaire hemimelie, tibiale verkorting, knie-instabiliteit en voetafwijkingen kunnen gelijktijdig voorkomen.\n\n"
        "Bij jonge kinderen kunnen de femurkop, femurhals en hun verbinding grotendeels uit kraakbeen bestaan en daardoor onzichtbaar zijn op conventionele radiografieën.\n\n"
        "Een herkenbaar acetabulum wijst op de aanwezigheid van een femurkop, maar acetabulaire dysplasie kan ook bij mildere vormen aanwezig zijn.\n\n"
        "Echografie en vooral MRI tonen de kraakbenige anatomie, de continuïteit tussen femurkop en femurschacht, de heupstabiliteit en de omliggende spieren en ligamenten.\n\n"
        "De anatomische classificatie en de voorspelde beenlengteongelijkheid op skeletale maturiteit bepalen welke reconstructieve of prothetische behandeling mogelijk is.\n"
        "Beleid\n"
        "Maak voor de behandelplanning een MRI en beoordeel de femurkop, de kraakbenige verbinding, het acetabulum, de heupstabiliteit en geassocieerde afwijkingen van knie, onderbeen en voet. De behandeling wordt individueel bepaald en kan bestaan uit reconstructie en beenverlenging, dan wel rotatieplastiek of amputatie met prothetische revalidatie bij een ernstige deficiëntie.\n"
        "Referenties\n"
        "1. Bernaerts A, Pouillon M, De Ridder K, Vanhoenacker F. Value of magnetic resonance imaging in early assessment of proximal focal femoral deficiency (PFFD). JBR-BTR. 2006;89(6):325-327.\n"
        "2. Anton CG, Applegate KE, Kuivila TE, Wilkes DC. Proximal femoral focal deficiency (PFFD): more than an abnormal hip. Semin Musculoskelet Radiol. 1999;3(3):215-226."
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
    "CORE-GU-020": (
        "Bevindingen\n"
        "De blanco CT toont gas in het parenchym van de transplantatienier. Een voornamelijk gashoudend abces breidt zich uit tot in de perirenale weke delen.\n\n"
        "Bij een andere patiënt blijft het gas beperkt tot het pyelocaliceale systeem, passend bij emfysemateuze pyelitis.\n"
        "Differentiaaldiagnose\n"
        "De differentiaaldiagnose van gas in de nier hangt af van de lokalisatie. Gas dat beperkt blijft tot het pyelocaliceale systeem kan berusten op emfysemateuze pyelitis, recente instrumentatie of een fistel met de darm. Bij deze patiënt bevindt het gas zich in het nierparenchym en breidt het zich uit naar de perinefrische ruimte, kenmerkend voor emfysemateuze pyelonefritis.\n"
        "Kernpunten\n"
        "Emfysemateuze pyelonefritis is een acute, fulminante en necrotiserende infectie van het nierparenchym en de perirenale weefsels.\n\n"
        "Ongeveer 80-96% van de patiënten heeft diabetes; ook immunosuppressie en urinewegobstructie zijn belangrijke risicofactoren.\n\n"
        "Escherichia coli is de meest voorkomende verwekker.\n\n"
        "De aandoening kan snel evolueren naar sepsis en overlijden; de totale mortaliteit bedraagt ongeveer 25%, met gerapporteerde waarden van 11-42%.\n\n"
        "Gas dat door infectie beperkt blijft tot het pyelocaliceale systeem wordt emfysemateuze pyelitis genoemd en heeft een betere prognose dan gas in het nierparenchym.\n\n"
        "Uitbreiding van gas of een gashoudend abces buiten de nier is prognostisch ongunstig; CT is de gevoeligste en specifiekste techniek om de aanwezigheid, lokalisatie en uitbreiding van het gas te beoordelen.\n"
        "Beleid\n"
        "Behandel met intraveneuze antibiotica, drainage van het abces en decompressie van een eventuele urinewegobstructie. Nefrectomie kan nodig zijn bij hoogrisicopatiënten of wanneer conservatieve behandeling faalt.\n"
        "Referenties\n"
        "Akhtar AL, Elsayes KM, Woodward S. AJR teaching file: diabetic patient presenting with right flank pain and fever. AJR Am J Roentgenol. 2010;194(6 suppl):WS31-33."
    ),
    "CORE-GU-044": (
        "Bevindingen\n"
        "Op de blanco CT van de eerste patiënt is hyperdens materiaal zichtbaar dat het linker nierbekken en pyelocaliceale systeem opvult en distendeert. Daarnaast is de rechternier atrofisch.\n\n"
        "Bij de tweede patiënt toont de blanco CT geen duidelijke laesie. In de nefropyelografische fase is in het rechter nierbekken een lineair vuldefect met spits toelopende randen zichtbaar.\n"
        "Differentiaaldiagnose\n"
        "De differentiaaldiagnose bij beide patiënten bestaat uit een bloedstolsel in het pyelocaliceale systeem en een urotheelcarcinoom. Een urotheelcarcinoom heeft een wekedelenattenuatie en neemt contrast op, terwijl een bloedstolsel meestal spontaan hyperdens is en geen contrast opneemt. Bij de eerste patiënt past het hyperdense materiaal in het pyelocaliceale systeem bij een groot bloedstolsel. Bij de tweede patiënt is de diagnose moeilijker, omdat de kleine laesie in het rechter nierbekken niet hyperdens is op de blanco CT. In de nefropyelografische fase wordt de laesie omgeven door hyperdens contrast, waardoor contrastopname moeilijk te beoordelen is. De lineaire configuratie, de spits toelopende randen en de grotendeels door contrast van het urotheel gescheiden ligging pleiten voor een retracterend bloedstolsel boven een urotheelcarcinoom.\n"
        "Kernpunten\n"
        "Bloedstolsels in het pyelocaliceale systeem kunnen voorkomen bij patiënten met hematurie.\n\n"
        "Een bloeding kan ontstaan door infectie, antistolling, een vasculaire malformatie, een iatrogene oorzaak of een onderliggende tumor.\n\n"
        "Een groot bloedstolsel kan een kleine onderliggende tumor maskeren.\n\n"
        "Op MRI kan een bloedstolsel een hoge T1-signaalintensiteit vertonen.\n"
        "Beleid\n"
        "Behandel de onderliggende oorzaak van de hematurie en sluit een onderliggende urotheeltumor uit.\n"
        "Referenties\n"
        "O’Connor OJ, Fitzgerald E, Maher MM. Imaging of hematuria. AJR Am J Roentgenol. 2010;195(4):W263-267."
    ),
    "CORE-GU-102": (
        "Bevindingen\n"
        "Grijswaarden- en kleuren-Doppleronderzoek van het linker scrotum toont meerdere gedilateerde, hypoechogene tubulaire structuren naast en craniaal van de linker testis, met aantoonbare veneuze flow.\n"
        "Differentiaaldiagnose\n"
        "De hypoechogene serpigineuze vaatstructuren zijn gedilateerde venen van de plexus pampiniformis. Deze venen liggen rond de testis en hebben normaal een diameter van ongeveer 1,5 mm. Een diameter groter dan 3 mm, met of zonder toename tijdens het Valsalva-manoeuvre, is diagnostisch voor een varicocèle.\n"
        "Kernpunten\n"
        "De meeste varicocèles zijn primair en ontstaan door insufficiënte kleppen in de gonadale venen; ze worden meestal vastgesteld tussen 15 en 25 jaar.\n\n"
        "Bij lichamelijk onderzoek voelt een varicocèle typisch aan als een zak met wormen.\n\n"
        "Een primaire varicocèle bevindt zich meestal links door het langere verloop van de linker vena testicularis en de loodrechte uitmonding in de vena renalis.\n\n"
        "Een secundaire varicocèle ontstaat door verhoogde druk in de gonadale vene, bijvoorbeeld bij een retroperitoneale massa, cirrose of portale hypertensie; een geïsoleerde rechtszijdige varicocèle vereist onderzoek naar retroperitoneale obstructie.\n\n"
        "Een klinische varicocèle kan samenhangen met mannelijke infertiliteit en een verminderd aantal zaadcellen; voor een uitsluitend op beeldvorming zichtbare subklinische varicocèle is die relatie niet overtuigend aangetoond.\n\n"
        "Dopplerechografie is zeer gevoelig; onderzoek in staande houding en tijdens het Valsalva-manoeuvre vergroot de zichtbaarheid van veneuze dilatatie en reflux.\n"
        "Beleid\n"
        "Behandel zo nodig met chirurgische ligatie of embolisatie.\n"
        "Referenties\n"
        "Dogra VS, Gottlieb RH, Oka M, Rubens DJ. Sonography of the scrotum. Radiology. 2003;227(1):18-36."
    ),
}
MAX_CHUNK_LENGTH = 3500
MEDICAL_REPLACEMENTS = (
    (r"\bSEH is\b", "Er is"),
    (r"\bSuperior Boogschutter Sinus\b", "sinus sagittalis superior"),
    (r"\bBoogschutters\b", "sagittaal"),
    (r"\bBoogschutter\b", "sagittaal"),
    (r"\bThis\b", "Dit"),
    (r"\bThese\b", "Deze"),
    (r"\bThose\b", "Die"),
    (r"\bIn patients\b", "Bij patiënten"),
    (r"\bpatients\b", "patiënten"),
    (r"\bPatient\b", "Patiënt"),
    (r"\bpatient\b", "patiënt"),
    (r"\bfeatures\b", "kenmerken"),
    (r"\bfeature\b", "kenmerk"),
    (r"\bfindings\b", "bevindingen"),
    (r"\bmanagement\b", "beleid"),
    (r"\bdiagnosis\b", "diagnose"),
    (r"\bHypothalamic Hamartoma\b", "Hypothalamisch hamartoom"),
    (r"\bDysembryoplastic Neuroepithelial Tumor\b", "Dysembryoplastische neuro-epitheliale tumor"),
    (r"\bHemimegalencephaly\b", "Hemimegalencefalie"),
    (r"\bChoroid Plexus Carcinoma\b", "Choroïdplexuscarcinoom"),
    (r"\bGliomatosis Cerebri\b", "Gliomatosis cerebri"),
    (r"\bTrigeminal Schwannoma\b", "Trigeminusschannoom"),
    (r"\bDirect Carotid-Cavernous Fistula\b", "Directe carotis-caverneuze fistel"),
    (r"\bLissencephaly\b", "Lissencefalie"),
    (r"\bHoloprosencephaly\b", "Holoprosencefalie"),
    (r"\bBand Heterotopia\b", "Bandheterotopie"),
    (r"\bEpidermoid Cyst\b", "Epidermoïdcyste"),
    (r"\bCavernous Malformation\b", "Caverneuze malformatie"),
    (r"\bHydranencephaly\b", "Hydranencefalie"),
    (r"\bSchizencephaly\b", "Schizencefalie"),
    (r"\bVon Hippel-Lindau Disease\b", "Ziekte van Von Hippel-Lindau"),
    (r"\bAcute Transverse Myelitis\b", "Acute transversale myelitis"),
    (r"\bDorsal Dermal Sinus\b", "Dorsale dermale sinus"),
    (r"\bSyringohydromyelia\b", "Syringohydromyelie"),
    (r"\bDiastematomyelia\b", "Diastematomyelie"),
    (r"\bCoalescent Mastoiditis\b", "Confluente mastoïditis"),
    (r"\bAntrochoanal Polyp\b", "Antrochoanale poliep"),
    (r"\bOcular Globe Rupture\b", "Ruptuur van de oogbol"),
    (r"\bCarotid Body Paraganglioma\b", "Paraganglioom van het carotislichaam"),
    (r"\bThyroglossal Duct Cyst\b", "Cyste van de ductus thyroglossus"),
    (r"\bOrbit Hemangioma\b", "Hemangioom van de orbita"),
    (r"\bLabyrinthitis Ossificans\b", "Ossificerende labyrintitis"),
    (r"\bOptic Neuritis\b", "Opticusneuritis"),
    (r"\bInflammatory Adenitis, Mycobacterium Avium Complex\b", "Inflammatoire adenitis door het Mycobacterium avium-complex"),
    (r"\bBrachial Plexus Neurofibroma\b", "Neurofibroom van de plexus brachialis"),
    (r"\bSEH is\b", "Er is"),
    (r"\bSEH zijn\b", "Er zijn"),
    (r"\bInverted papilloma\b", "Invers papilloom"),
    (r"\bFocal gliomas\b", "Focale gliomen"),
    (r"\bOverall\b", "Over het algemeen"),
    (r"\btumors\b", "tumoren"),
    (r"\bfreebase form\b", "freebasevorm"),
    (r"\bPresents\b", "presenteert zich"),
    (r"\bNeeds\b", "heeft behoefte aan"),
    (r"\bPelvic Mass\b", "bekkenmassa"),
    (r"\bPelvic\b", "bekken"),
    (r"\bColon Cancer\b", "coloncarcinoom"),
    (r"\bStatus Post\b", "status na"),
    (r"\bBiliaire Wand stent Plaatsing 4 Maanden Ago\b", "plaatsing van een biliaire wandstent vier maanden geleden"),
    (r"\bBiliaire Wand stent Plaatsing\b", "plaatsing van een biliaire wandstent"),
    (r"\bSeveral-Month History of Chronische Bilaterale Leg Swelling met 1 Week of Acute Verergering\b", "voorgeschiedenis van enkele maanden met chronische bilaterale zwelling van de benen en één week acute verergering"),
    (r"\bInwoning Permanente Inferior Vena Cava Filter geplaatst 6 jaar Prior\b", "een permanent aanwezige vena-cava-inferiorfilter, zes jaar eerder geplaatst"),
    (r"\bLeg Swelling\b", "zwelling van de benen"),
    (r"\bSeveral-Month History\b", "voorgeschiedenis van enkele maanden"),
    (r"\bHistory of\b", "voorgeschiedenis van"),
    (r"\bPrior\b", "eerder"),
    (r"\bAgo\b", "geleden"),
    (r"\bAccess Device\b", "toegangssysteem"),
    (r"\bVascular Access\b", "vasculaire toegang"),
    (r"\bmislukte Ureterale stent\b", "mislukte plaatsing van een ureterstent"),
    (r"\bInferior Vena Cava stent Acute bij chronische trombose\b", "stent in de vena cava inferior bij acute trombose bovenop chronische trombose"),
    (r"\bFindings\b", "Bevindingen"),
    (r"\bDifferential Diagnosis\b", "Differentiaaldiagnose"),
    (r"\bTeaching Points\b", "Kernpunten"),
    (r"\bManagement\b", "Beleid"),
    (r"\bFurther Readings?\b", "Referenties"),
    (r"\bHerpes Encephalitis\b", "Herpesencefalitis"),
    (r"\bCerebral Venous Thrombosis and Infarction\b", "Cerebrale veneuze trombose en infarcering"),
    (r"\bEncephalitis\b", "Encefalitis"),
    (r"\bencephalitis\b", "encefalitis"),
    (r"\bhemorrhage\b", "bloeding"),
    (r"\bischemia\b", "ischemie"),
    (r"\binfarction\b", "infarcering"),
    (r"\binfarct\b", "infarct"),
    (r"\bFindings\b", "Bevindingen"),
    (r"\bImaging\b", "Beeldvorming"),
    (r"\bimage\b", "beeld"),
    (r"\bimages\b", "beelden"),
    (r"\bpresents to the (?:ED|ER)\b", "presenteert zich op de SEH"),
    (r"\bpresenting to the (?:ED|ER)\b", "met presentatie op de SEH"),
    (r"\bto the (?:ED|ER)\b", "op de SEH"),
    (r"\bThere is\b", "Er is"),
    (r"\bThere are\b", "Er zijn"),
    (r"\bwith\b", "met"),
    (r"\band\b", "en"),
    (r"\bthe\b", "de"),
    (r"\bof the\b", "van de"),
    (r"\bright\b", "rechter"),
    (r"\bleft\b", "linker"),
    (r"\bsmall\b", "kleine"),
    (r"\blarge\b", "grote"),
    (r"\bnormal\b", "normale"),
    (r"\bacute\b", "acute"),
    (r"\bchronic\b", "chronische"),
    (r"\bconsistent with\b", "passend bij"),
    (r"\bassociated with\b", "geassocieerd met"),
    (r"\bdue to\b", "als gevolg van"),
    (r"\bcan be seen\b", "kan worden gezien"),
    (r"\bshows\b", "toont"),
    (r"\bdemonstrates\b", "toont"),
    (r"\breveals\b", "toont"),
    (r"\bdiagnosis\b", "diagnose"),
    (r"\bdiagnostic\b", "diagnostische"),
    (r"\bmanagement\b", "beleid"),
    (r"\bTumor\b", "Tumor"),
    (r"\bPineoblastomas\b", "Pineoblastomen"),
    (r"\bPineoblastoma\b", "Pineoblastoom"),
    (r"\bPineocytoma\b", "Pineocytoom"),
    (r"\bMeningioma\b", "Meningeoom"),
    (r"\bGlioma\b", "Glioom"),
    (r"\bLymphoma\b", "Lymfoom"),
    (r"\bCerebral\b", "Cerebrale"),
    (r"\bvenous\b", "veneuze"),
    (r"\bthrombosis\b", "trombose"),
    (r"\bseizures\b", "epileptische aanvallen"),
    (r"\bseizure\b", "epileptische aanval"),
    (r"\bberekeningen\b", "verkalkingen"),
    (r"\bberekening\b", "verkalking"),
    (r"\bcalculatory['’]?s\b", "verkalkingen"),
    (r"\binvlouerende\b", "involuerende"),
    (r"\bfibrodenomas\b", "fibroadenomen"),
    (r"\bfibrodenoom\b", "fibroadenoom"),
    (r"\bfibradenomen\b", "fibroadenomen"),
    (r"\bductal carcinoom\b", "ductaal carcinoom"),
    (r"\bductalcarcinoom\b", "ductaal carcinoom"),
    (r"\bductaalcarcinoom\b", "ductaal carcinoom"),
    (r"\bkanaalcarcinoom\b", "ductaal carcinoom"),
    (r"\bdarmkanker\b", "ductaal carcinoom"),
    (r"\baxillary\b", "axillair"),
    (r"\bokillaire\b", "axillaire"),
    (r"\bokillary\b", "axillaire"),
    (r"\blymf knooppunt\b", "lymfeklier"),
    (r"\blymf knoop\b", "lymfeklier"),
    (r"\blymfknoop\b", "lymfeklier"),
    (r"\blumbectomie\b", "lumpectomie"),
    (r"\blumbecomy\b", "lumpectomie"),
    (r"\bclombectomie\b", "lumpectomie"),
    (r"\bmammagram\b", "mammogram"),
    (r"\bmammagram\b", "mammogram"),
    (r"\bgeheime verkalkingen\b", "secretoire verkalkingen"),
    (r"\bsarcoma\b", "sarcoom"),
    (r"\bsternalis muscle\b", "musculus sternalis"),
    (r"\bsebaceous cyst\b", "talgcyste"),
    (r"\bSEH is\b", "Er is"),
    (r"\bSEH zijn\b", "Er zijn"),
)


def preserve_initial_case(source, replacement):
    return replacement[:1].upper() + replacement[1:] if source[:1].isupper() else replacement


def polish_translation(text):
    polished = text or ""
    for pattern, replacement in MEDICAL_REPLACEMENTS:
        polished = re.sub(
            pattern,
            lambda match: preserve_initial_case(match.group(0), replacement),
            polished,
            flags=re.IGNORECASE,
        )
    return polished


def split_chunks(text):
    if len(text) <= MAX_CHUNK_LENGTH:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > MAX_CHUNK_LENGTH:
        split_at = max(
            remaining.rfind("\n", 0, MAX_CHUNK_LENGTH),
            remaining.rfind(". ", 0, MAX_CHUNK_LENGTH),
        )
        if split_at < MAX_CHUNK_LENGTH // 2:
            split_at = MAX_CHUNK_LENGTH
        else:
            split_at += 1
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def translate_text(text):
    text = (text or "").strip()
    if not text:
        return ""
    translated = "\n".join(
        translate.translate(chunk, "en", "nl")
        for chunk in split_chunks(text)
    )
    translated = translated[:1].upper() + translated[1:] if translated else translated
    return polish_translation(translated)


def translate_answer_details(text):
    sections = []
    current_heading = None
    current_lines = []

    def append_section():
        if not current_heading:
            return
        content = "\n".join(current_lines).strip()
        section_key = SECTION_HEADINGS[current_heading]
        translated = content if section_key == "references" else translate_text(content)
        sections.append(f"{SECTION_HEADINGS_NL[section_key]}\n{translated}".strip())

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        matched_heading = next(
            (heading for heading in SECTION_HEADINGS if line.lower() == heading.lower()),
            None,
        )
        if matched_heading:
            append_section()
            current_heading = matched_heading
            current_lines = []
        elif current_heading:
            current_lines.append(raw_line)
    append_section()
    return "\n".join(sections)


def translate_card(card, existing):
    card_id = card["id"]
    return card_id, {
        "history": polish_translation(
            MANUAL_HISTORY_TRANSLATIONS.get(card_id)
            or existing.get("histories", {}).get(card_id)
            or translate_text(card.get("history", ""))
        ),
        "diagnosis": polish_translation(
            MANUAL_DIAGNOSIS_TRANSLATIONS.get(card_id)
            or existing.get("diagnoses", {}).get(card_id)
            or translate_text(card.get("diagnosis", ""))
        ),
        "answer_details": (
            MANUAL_ANSWER_TRANSLATIONS.get(card_id)
            or existing.get("answer_details", {}).get(card_id)
            or translate_answer_details(card.get("answer_details", ""))
        ),
    }


def write_output(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def translate_section(section_key, workers):
    source_path = ROOT / "data" / f"core_{section_key}.json"
    output_path = ROOT / "data" / f"core_{section_key}_nl.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    existing = (
        json.loads(output_path.read_text(encoding="utf-8"))
        if output_path.exists()
        else {}
    )
    output = {
        "histories": dict(existing.get("histories", {})),
        "diagnoses": dict(existing.get("diagnoses", {})),
        "answer_details": dict(existing.get("answer_details", {})),
    }
    cards = source.get("cards", [])

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(translate_card, card, existing): card["id"]
            for card in cards
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            card_id, translated = future.result()
            output["histories"][card_id] = translated["history"]
            output["diagnoses"][card_id] = translated["diagnosis"]
            output["answer_details"][card_id] = translated["answer_details"]
            if completed % 10 == 0 or completed == len(cards):
                write_output(output_path, output)
                print(f"{section_key}: {completed}/{len(cards)}", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Build complete Dutch translations for CORE case content."
    )
    parser.add_argument(
        "sections",
        nargs="*",
        default=["gastrointestinal", "genitourinary", "breast"],
    )
    parser.add_argument("--workers", type=int, default=4)
    arguments = parser.parse_args()
    for section in arguments.sections:
        translate_section(section, max(1, min(arguments.workers, 6)))


if __name__ == "__main__":
    main()
