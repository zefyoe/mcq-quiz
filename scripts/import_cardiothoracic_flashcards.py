import csv
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "static" / "images" / "cardiothoracic"
OUTPUT = ROOT / "data" / "cardiothoracic_flashcards.json"


TRANSLATIONS = {
    "papillary muscle of left ventricle": "papillaire spier van de linkerventrikel",
    "inferior vena cava": "vena cava inferior",
    "abdominal aorta": "abdominale aorta",
    "posterior leaflet of mitral valve": "posterieur mitraliskleplichaam",
    "interventricular septum – muscular portion": "musculair deel van het interventriculaire septum",
    "myocardium of left ventricle": "myocardium van de linkerventrikel",
    "right main pulmonary artery": "rechter hoofdlongslagader",
    "right main bronchus": "rechter hoofdbronchus",
    "right pectoralis minor": "rechter musculus pectoralis minor",
    "main pulmonary artery": "hoofdlongslagader",
    "right atrial appendage": "rechter hartoor",
    "left hemidiaphragm": "linker hemidiafragma",
    "body of sternum": "corpus van het sternum",
    "right hemidiaphragm": "rechter hemidiafragma",
    "left main bronchus": "linker hoofdbronchus",
    "lateral border of right lobe of thymus": "laterale rand van de rechter thymuskwab",
    "left cardiophrenic recess": "linker cardiophrenische recessus",
    "anterior junctional line": "anterieure junctielijn",
    "right paratracheal stripe": "rechter paratracheale streep",
    "aortic knuckle": "aortaknobbel",
    "arch of aorta": "aortaboog",
    "left common carotid artery": "linker arteria carotis communis",
    "brachiocephalic artery": "truncus brachiocephalicus",
    "right brachiocephalic vein": "rechter vena brachiocephalica",
    "ascending thoracic aorta": "thoracale aorta ascendens",
    "left pulmonary artery": "linker longslagader",
    "anterior segmental bronchus of right upper lobe": "anterieure segmentbronchus van de rechter bovenkwab",
    "left greater fissure": "linker grote fissuur",
    "thoracic oesophagus": "thoracale oesofagus",
    "manubriosternal joint": "manubriosternale gewricht",
    "appendage of right atrium": "aanhangsel van het rechter atrium",
    "right coronary sinus": "rechter coronair sinus",
    "left inferior lobar bronchus": "linker onderste lobaire bronchus",
    "right lower lobe bronchus": "bronchus van de rechter onderkwab",
    "azygos vein": "vena azygos",
    "right superior pulmonary vein": "rechter vena pulmonalis superior",
    "left atrium": "linker atrium",
    "trachea": "trachea",
    "non-coronary sinus of the aorta": "non-coronaire sinus van de aorta",
    "muscular portion of the interventricular septum": "musculair deel van het interventriculaire septum",
    "left superior pulmonary vein": "linker vena pulmonalis superior",
    "superior vena cava": "vena cava superior",
    "right atrium": "rechter atrium",
    "right horizontal fissure": "rechter horizontale fissuur",
    "oblique fissure of right lung": "schuine fissuur van de rechterlong",
    "apical segment of right upper lobe": "apicaal segment van de rechter bovenkwab",
    "right middle lobe": "rechter middenkwab",
    "left descending interlobar pulmonary artery": "linker dalende interlobaire longslagader",
    "descending thoracic aorta": "thoracale aorta descendens",
    "gastric fundus": "fundus van de maag",
    "right subclavian vein": "rechter vena subclavia",
    "xiphoid process of sternum": "processus xiphoideus van het sternum",
    "right bronchus intermedius": "rechter bronchus intermedius",
    "posterior basal segment of the right lower lobe": "posterieur basaal segment van de rechter onderkwab",
    "superior bronchus of left upper lobe": "superieure bronchus van de linker bovenkwab",
    "left upper lobe apicoposterior segment": "apicoposterieur segment van de linker bovenkwab",
    "pericardial sac": "pericardiale zak",
    "left subclavian artery": "linker arteria subclavia",
    "right anterior segmental upper lobe bronchus": "rechter anterieure segmentbronchus van de bovenkwab",
    "posterior basal segmental bronchus of right lower lobe": "posterieur basale segmentbronchus van de rechter onderkwab",
    "superior segmental bronchus of lingular lobe": "superieure segmentbronchus van de lingulakwab",
    "lingular segmental bronchus of left upper lobe": "lingulaire segmentbronchus van de linker bovenkwab",
    "papillary muscle of the left ventricle": "papillaire spier van de linkerventrikel",
    "anterior interventricular branch of left coronary artery": "ramus interventricularis anterior van de linker coronairarterie",
    "left costodiaphragmatic recess": "linker costodiafragmatische recessus",
    "right subclavian artery": "rechter arteria subclavia",
    "right upper lobe pulmonary vein": "vena pulmonalis van de rechter bovenkwab",
    "non-coronary cusp of aortic valve": "non-coronaire cusp van de aortaklep",
    "circumflex branch of the left coronary artery": "ramus circumflexus van de linker coronairarterie",
    "right main coronary artery": "rechter hoofdstam van de coronairarterie",
    "aberrant right subclavian artery": "aberrante rechter arteria subclavia",
    "common origin of brachiocephalic and left common carotid artery": "gemeenschappelijke oorsprong van de truncus brachiocephalicus en linker arteria carotis communis",
    "pectus excavatum": "pectus excavatum",
    "left main pulmonary artery": "linker hoofdlongslagader",
    "right costodiaphragmatic recess": "rechter costodiafragmatische recessus",
    "epicardium of the left ventricle": "epicardium van de linkerventrikel",
    "left ventricular cavity": "cavum van de linkerventrikel",
    "right ventricular cavity": "cavum van de rechterventrikel",
    "membranous portion of intreventricular septum": "membraneuze deel van het interventriculaire septum",
    "aortic vestibule": "aortavestibulum",
    "right inferior pulmonary vein": "rechter vena pulmonalis inferior",
    "left pectoralis major": "linker musculus pectoralis major",
    "spinal cord within the spinal canal": "ruggenmerg in het wervelkanaal",
    "chordae tendineae in left ventricle": "chordae tendineae in de linkerventrikel",
    "tracheal ring cartilage": "kraakbeen van een trachearing",
    "right cardiodiaphragmatic recess": "rechter cardiodiafragmatische recessus",
    "aortic pulmonary window": "aortopulmonaal venster",
    "carina": "carina",
    "left ventricular border": "linker ventriculaire contour",
    "azygo-esophageal recess": "azygo-oesofageale recessus",
    "azygo-oesophageal recess": "azygo-oesofageale recessus",
    "left internal thoracic artery": "linker arteria thoracica interna",
    "left cervical rib": "linker cervicale rib",
    "right ventricle": "rechterventrikel",
    "left inferior pulmonary vein": "linker vena pulmonalis inferior",
    "left superior lobar bronchus": "linker superieure lobaire bronchus",
    "left superior segmental lingular bronchus": "linker superieure segmentbronchus van de lingula",
    "cusps of aortic valve": "cusps van de aortaklep",
    "left ventricular outflow tract": "linker ventriculaire uitstroomtractus",
    "anterior sinus of valsalva": "anterieure sinus van Valsalva",
    "muscular part of interventricular septum": "musculair deel van het interventriculaire septum",
    "oblique fissure of the left lung": "schuine fissuur van de linkerlong",
    "right greater fissure": "rechter grote fissuur",
    "right superior lobar pulmonary artery": "rechter superieure lobaire longslagader",
    "aortic pulmonary window": "aortopulmonaal venster",
    "manubrium of sternum": "manubrium van het sternum",
    "dome of right hemidiaphragm": "koepel van het rechter hemidiafragma",
    "coronary sinus": "sinus coronarius",
    "medial basal segmental bronchus of right lower lobe": "mediale basale segmentbronchus van de rechter onderkwab",
    "right medial segmental bronchus of middle lobe": "rechter mediale segmentbronchus van de middenkwab",
    "right middle lobar bronchus": "bronchus van de rechter middenkwab",
    "posterior segment of right upper lobe bronchus": "bronchus van het posterieure segment van de rechter bovenkwab",
    "anterior segmental bronchus of left upper lobe": "anterieure segmentbronchus van de linker bovenkwab",
    "left lower lobe superior segmental bronchus": "superieure segmentbronchus van de linker onderkwab",
    "posterior basal segmental bronchus of left lower lobe": "posterieur basale segmentbronchus van de linker onderkwab",
    "basal lateral segmental bronchus of left lower lobe": "laterale basale segmentbronchus van de linker onderkwab",
    "posterior junctional line": "posterieure junctielijn",
    "right brachiocephalic artery": "rechter truncus brachiocephalicus",
    "left internal thoracic artery": "linker arteria thoracica interna",
    "azygos lobe": "azygoskwab",
    "right cervical rib": "rechter cervicale rib",
    "anterior leaflet of mitral valve": "anterieur mitraliskleplichaam",
    "cerebrospinal fluid in the thoracic spinal canal": "cerebrospinale vloeistof in het thoracale wervelkanaal",
    "descending interlobar pulmonary artery": "dalende interlobaire longslagader",
    "left atrial appendage": "linker hartoor",
    "companion shadow over left clavicle": "begeleidende schaduw boven de linker clavicula",
    "lateral border of right atrium": "laterale rand van het rechter atrium",
    "left brachiocephalic vein": "linker vena brachiocephalica",
    "right sinus of valsava": "rechter sinus van Valsalva",
    "thoracic descending aorta": "thoracale aorta descendens",
    "lingula segment of left upper lobe": "lingulasegment van de linker bovenkwab",
    "anterior basal segmental bronchus of right lower lobe": "anterieure basale segmentbronchus van de rechter onderkwab",
    "lateral basal segmental bronchus of right lower lobe": "laterale basale segmentbronchus van de rechter onderkwab",
    "right lower lobe superior segmental bronchus": "superieure segmentbronchus van de rechter onderkwab",
    "right lateral segmental bronchus of middle lobe": "rechter laterale segmentbronchus van de middenkwab",
    "left anteromedial basal segmental bronchus": "linker anteromediale basale segmentbronchus",
    "left lower lobe anterior segmental bronchus": "anterieure segmentbronchus van de linker onderkwab",
    "lingular segment of left upper lobe": "lingulasegment van de linker bovenkwab",
    "aortic valves": "aortakleppen",
    "right axillary vein": "rechter vena axillaris",
    "azygos arch": "azygosboog",
    "hemiazygos vein": "vena hemiazygos",
    "right paravertebral stripe": "rechter paravertebrale streep",
    "azygos fissure": "azygosfissuur",
    "right sided aortic arch with aberrant left subclavian artery": "rechtszijdige aortaboog met aberrante linker arteria subclavia",
    "tracheal bronchus": "tracheale bronchus",
}


def answer_label(raw_answer):
    return raw_answer.rsplit(" - ", 1)[0].strip()


def extract_cards():
    cards = []
    for archive in sorted(SOURCE_DIR.glob("cardiothoracic_*.zip")):
        set_name = archive.stem
        destination = SOURCE_DIR / set_name
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as source_zip:
            source_zip.extractall(destination)
            with source_zip.open("manifest.csv") as manifest_file:
                rows = csv.DictReader(
                    line.decode("utf-8-sig", errors="replace")
                    for line in manifest_file
                )
                for row in rows:
                    english_answer = answer_label(row["answer"])
                    dutch_answer = TRANSLATIONS.get(english_answer.lower())
                    if not dutch_answer:
                        raise ValueError(f"Missing Dutch translation: {english_answer}")
                    card_number = len(cards) + 1
                    cards.append({
                        "id": f"CT{card_number:03d}",
                        "category": "Anatomy - Cardiothoracic",
                        "question": "Which anatomical structure is indicated?",
                        "question_nl": "Welke anatomische structuur is aangeduid?",
                        "answer": english_answer,
                        "answer_nl": dutch_answer,
                        "image": f"cardiothoracic/{set_name}/{row['filename']}",
                        "source_set": set_name,
                        "source_question": row["question"],
                    })
    return cards


def main():
    cards = extract_cards()
    if len(cards) != 258:
        raise ValueError(f"Expected 258 cardiothoracic cards, got {len(cards)}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps({"section": "cardiothoracic", "cards": cards}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Imported {len(cards)} cardiothoracic flashcards.")


if __name__ == "__main__":
    main()
