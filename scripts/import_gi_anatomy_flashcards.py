import csv
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "static" / "images"
OUTPUT = ROOT / "data" / "gastrointestinal_anatomy_flashcards.json"


TRANSLATIONS = {
    "gallbladder": "galblaas",
    "azygos vein": "vena azygos",
    "hepatic flexure of large bowel": "flexura hepatica van het colon",
    "second liver segment": "tweede leversegment",
    "intrahepatic portal vein": "intrahepatische poortader",
    "ileocaecal valve": "ileocaecale klep",
    "descending portion of duodenum": "dalend deel van het duodenum",
    "right transversus abdominis": "rechter musculus transversus abdominis",
    "crus of right hemidiaphragm": "crus van het rechter hemidiafragma",
    "right twelfth rib": "rechter twaalfde rib",
    "superior mesenteric vein": "vena mesenterica superior",
    "posterior branch of right portal vein": "posterieure tak van de rechter poortader",
    "third liver segment": "derde leversegment",
    "body of stomach": "corpus van de maag",
    "rectum": "rectum",
    "superior mesenteric artery": "arteria mesenterica superior",
    "left gastric artery": "arteria gastrica sinistra",
    "left renal vein": "linker vena renalis",
    "neck of pancreas": "collum van de pancreas",
    "spleen": "milt",
    "posterior branch of left internal iliac artery": "posterieure tak van de linker arteria iliaca interna",
    "portal venous confluence": "confluens van de poortader",
    "portal vein confluence": "confluens van de poortader",
    "anterior branch of right portal vein": "anterieure tak van de rechter poortader",
    "body of gallbladder": "corpus van de galblaas",
    "fundus of the stomach": "fundus van de maag",
    "superior vena cava": "vena cava superior",
    "pyloric antrum of the stomach": "antrum pyloricum van de maag",
    "common hepatic duct": "ductus hepaticus communis",
    "anal canal": "anaalkanaal",
    "linea alba": "linea alba",
    "right ischiorectal fossa": "rechter fossa ischiorectalis",
    "main pancreatic duct": "ductus pancreaticus principalis",
    "riedel lobe of liver": "Riedel-kwab van de lever",
    "fundus of gallbladder": "fundus van de galblaas",
    "abdominal aorta": "abdominale aorta",
    "inferior vena cava": "vena cava inferior",
    "cerebrospinal fluid in the spinal canal": "cerebrospinaal vocht in het wervelkanaal",
    "prevesical space": "prevesicale ruimte",
    "caecum": "caecum",
    "gallbladder fundus": "fundus van de galblaas",
    "right posterior branch of portal vein": "rechter posterieure tak van de poortader",
    "cystic duct": "ductus cysticus",
    "common bile duct": "ductus choledochus",
    "left suprarenal gland": "linker bijnier",
    "head of the pancreas": "caput van de pancreas",
    "descending thoracic aorta": "thoracale aorta descendens",
    "inferior mesenteric vein": "vena mesenterica inferior",
    "splenic vein": "vena splenica",
    "extrahepatic portal vein": "extrahepatische poortader",
    "hepatic segment of inferior vena cava": "hepatisch segment van de vena cava inferior",
    "left common iliac vein": "linker vena iliaca communis",
    "middle hepatic vein": "vena hepatica media",
    "right upper pole renal cortex": "niercortex van de rechter bovenpool",
    "uncinate process of pancreas": "processus uncinatus van de pancreas",
    "coeliac artery": "arteria coeliaca",
    "common hepatic artery": "arteria hepatica communis",
    "left tenth posterior rib": "linker tiende posterieure rib",
    "gastro-oesophageal junction": "gastro-oesofageale overgang",
    "lower oesophageal sphincter": "onderste oesofagussfincter",
    "cardia of stomach": "cardia van de maag",
    "lesser curvature of stomach": "kleine curvatuur van de maag",
    "pyloric sphincter of stomach": "pylorussfincter van de maag",
    "first part of duodenum": "eerste deel van het duodenum",
    "pylorus of stomach": "pylorus van de maag",
    "greater curvature of the stomach": "grote curvatuur van de maag",
    "gas bubble in stomach": "gasbel in de maag",
    "ascending colon": "colon ascendens",
    "thoracic oesophagus": "thoracale oesofagus",
    "oesophageal impression from left main bronchus": "oesofageale impressie door de linker hoofdbronchus",
    "oesophageal contour from left atrium impression": "oesofageale contour door impressie van het linker atrium",
    "replaced right hepatic artery": "vervangende rechter arteria hepatica",
    "right gonadal vein": "rechter gonadale vene",
    "left portal vein": "linker poortadertak",
    "splenic flexure of large bowel": "flexura lienalis van het colon",
    "left external iliac artery": "linker arteria iliaca externa",
    "segment seven of liver": "zevende leversegment",
    "left renal artery": "linker arteria renalis",
    "inferior mesenteric artery": "arteria mesenterica inferior",
    "duplication of the inferior vena cava": "duplicatie van de vena cava inferior",
    "terminal ileum": "terminale ileum",
    "body of pancreas": "corpus van de pancreas",
    "left inferior gluteal artery": "linker arteria glutea inferior",
    "left internal iliac artery": "linker arteria iliaca interna",
    "right diaphragmatic crus": "rechter crus diaphragmaticum",
    "right common iliac artery": "rechter arteria iliaca communis",
    "left common iliac artery": "linker arteria iliaca communis",
    "right main branch of portal vein": "rechter hoofdstam van de poortader",
    "right hemidiaphragm": "rechter hemidiafragma",
    "fundus of stomach": "fundus van de maag",
    "antrum of stomach": "antrum van de maag",
    "descending colon": "colon descendens",
    "prevertebral soft tissue": "prevertecale weke delen",
    "urinary bladder": "urineblaas",
    "oesophageal contour from aortic arch impression": "oesofageale contour door impressie van de aortaboog",
    "splenic artery": "arteria splenica",
    "retroaortic left renal vein": "retroaortale linker vena renalis",
    "small intestine loops": "darmlissen van de dunne darm",
    "left external oblique": "linker musculus obliquus externus abdominis",
    "left internal oblique": "linker musculus obliquus internus abdominis",
    "small bowel mesenteric vessels": "mesenteriale vaten van de dunne darm",
    "greater curvature of stomach": "grote curvatuur van de maag",
    "hilum of the spleen": "hilum van de milt",
    "head of pancreas": "caput van de pancreas",
    "falciform ligament of the liver": "ligamentum falciforme van de lever",
    "tail of pancreas": "cauda van de pancreas",
    "right external oblique": "rechter musculus obliquus externus abdominis",
    "right inguinal canal": "rechter canalis inguinalis",
    "transverse colon": "colon transversum",
    "horizontal portion of duodenum": "horizontaal deel van het duodenum",
    "left psoas major": "linker musculus psoas major",
    "left psoas minor": "linker musculus psoas minor",
    "common coeliacomesenteric trunk": "truncus coeliacomesentericus",
    "rugal folds of stomach": "rugae van de maag",
    "ligamentum teres hepatis": "ligamentum teres hepatis",
    "perirectal space": "perirectale ruimte",
    "left hepatic duct": "ductus hepaticus sinister",
    "right intrahepatic bile duct": "rechter intrahepatische galweg",
    "lumbar intervertebral disc": "lumbale tussenwervelschijf",
    "lower pole of the spleen": "onderpool van de milt",
    "segment 6 of right hepatic lobe": "segment 6 van de rechter leverkwab",
    "left rectus abdominis": "linker musculus rectus abdominis",
    "right linea semilunaris": "rechter linea semilunaris",
    "sacral vertebral body": "corpus van een sacrale wervel",
    "left uterosacral ligament": "linker ligamentum uterosacrale",
    "right peritoneal lining": "rechter peritoneale bekleding",
    "tail of the pancreas": "cauda van de pancreas",
    "body of the pancreas": "corpus van de pancreas",
    "left gonadal vein": "linker gonadale vene",
    "right hepatic vein": "rechter vena hepatica",
    "left hepatic vein": "linker vena hepatica",
    "hepatic portal vein branch": "tak van de vena portae hepatis",
    "left lobe of liver": "linker leverkwab",
    "caudate lobe of liver": "caudatuskwab van de lever",
    "rugal fold in body of stomach": "maagplooi in het corpus van de maag",
    "transverse colon haustral folds": "haustra van het colon transversum",
    "lumbar arteries": "lumbale arteriën",
    "coeliac trunk": "truncus coeliacus",
    "right posterior rectus sheath": "rechter posterieure rectusschede",
    "left transversus abdominis": "linker musculus transversus abdominis",
    "transposition of inferior vena cava": "transpositie van de vena cava inferior",
}


def answer_label(raw_answer):
    return raw_answer.rsplit(" - ", 1)[0].strip()


def import_cards():
    cards = []
    for archive in sorted(SOURCE_DIR.glob("GI_*.zip")):
        set_name = archive.stem
        destination = SOURCE_DIR / set_name
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as source_zip:
            source_zip.extractall(destination)
            rows = csv.DictReader(
                line.decode("utf-8-sig", errors="replace")
                for line in source_zip.open("manifest.csv")
            )
            for row in rows:
                english_answer = answer_label(row["answer"])
                dutch_answer = TRANSLATIONS.get(english_answer.lower())
                if not dutch_answer:
                    raise ValueError(f"Missing Dutch translation: {english_answer}")
                number = len(cards) + 1
                cards.append({
                    "id": f"GI{number:03d}",
                    "category": "Anatomy - Gastrointestinal",
                    "question": "Which anatomical structure is indicated?",
                    "question_nl": "Welke anatomische structuur is aangeduid?",
                    "answer": english_answer,
                    "answer_nl": dutch_answer,
                    "image": f"{set_name}/{row['filename']}",
                    "source_set": set_name,
                    "source_question": row["question"],
                })
    return cards


def main():
    cards = import_cards()
    if len(cards) != 248:
        raise ValueError(f"Expected 248 gastrointestinal cards, got {len(cards)}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps({"section": "gastrointestinal", "cards": cards}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Imported {len(cards)} gastrointestinal anatomy flashcards.")


if __name__ == "__main__":
    main()
