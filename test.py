import random

# 📝 1️⃣ Vraagbank
# Voeg hier je vragen toe. Elke vraag is een dictionary.
questions = [
    {
        "ID": "Q001",
        "Category": "Anatomy",
        "Vraag": "Wat is 2 + 2?",
        "A": "3",
        "B": "4",
        "C": "5",
        "D": "6",
        "Correct": "B"
    },
    {
        "ID": "Q002",
        "Category": "Anatomy",
        "Vraag": "Wat is de hoofdstad van Frankrijk?",
        "A": "Berlijn",
        "B": "Londen",
        "C": "Parijs",
        "D": "Rome",
        "Correct": "C"
    },
    {
        "ID": "Q003",
        "Category": "Anatomy",
        "Vraag": "Welke kleur krijg je bij rood + geel?",
        "A": "Groen",
        "B": "Paars",
        "C": "Oranje",
        "D": "Blauw",
        "Correct": "C"
    },
    {
        "ID": "Q004",
        "Category": "Anatomy",
        "Vraag": "Wie schreef 'Harry Potter'?",
        "A": "J.R.R. Tolkien",
        "B": "J.K. Rowling",
        "C": "George R.R. Martin",
        "D": "Suzanne Collins",
        "Correct": "B"
    },
    {
        "ID": "Q005",
        "Category": "Anatomy",
        "Vraag": "Wat is de grootste planeet in ons zonnestelsel?",
        "A": "Aarde",
        "B": "Mars",
        "C": "Jupiter",
        "D": "Saturnus",
        "Correct": "C"
    },
    {
        "ID": "Q006",
        "Category": "Physics",
        "Vraag": "La fréquence d'une sonde échographique influence principalement :",
        "A": "La profondeur de pénétration",
        "B": "La résolution spatiale",
        "C": "L'impédance acoustique",
        "D": "La vitesse de propagation",
        "Correct": ["A", "B"]
    },
    {
        "ID": "Q007",
        "Category": "Physics",
        "Vraag": "L'impédance acoustique dépend de :",
        "A": "La densité du tissu",
        "B": "La vitesse du son dans le tissu",
        "C": "La fréquence de la sonde",
        "D": "Le gain",
        "Correct": ["A", "B"]
    },
    {
        "ID": "Q008",
        "Category": "Physics",
        "Vraag": "L'artéfact de renforcement postérieur est dû à :",
        "A": "Une réflexion totale",
        "B": "Une faible atténuation du faisceau",
        "C": "Une diffusion excessive",
        "D": "Un mauvais réglage du TGC",
        "Correct": "B"
    },
    {
        "ID": "Q009",
        "Category": "Physics",
        "Vraag": "L'ombre acoustique postérieure se produit typiquement derrière :",
        "A": "Un kyste",
        "B": "Une calcification",
        "C": "Une structure liquide",
        "D": "Une veine",
        "Correct": "B"
    },
    {
        "ID": "Q010",
        "Category": "Physics",
        "Vraag": "Le Doppler couleur permet d'évaluer :",
        "A": "La vitesse absolue exacte",
        "B": "La direction du flux",
        "C": "Le volume sanguin",
        "D": "La fréquence d'émission",
        "Correct": "B"
    }
]

# 🏁 2️⃣ Functie om quiz af te nemen
def take_quiz(questions):
    score = 0
    random.shuffle(questions)  # Willekeurige volgorde van vragen
    
    for i, q in enumerate(questions):
        print(f"\n{q['ID']} - Vraag {i+1}: {q['Vraag']}")
        print(f"A. {q['A']}")
        print(f"B. {q['B']}")
        print(f"C. {q['C']}")
        print(f"D. {q['D']}")
        
        answer = input("Jouw antwoord (A/B/C/D): ").strip().upper()
        
        # Support both single answer (string) and multiple answers (list)
        correct_answers = q["Correct"] if isinstance(q["Correct"], list) else [q["Correct"]]
        
        if answer in correct_answers:
            print("✅ Correct!")
            score += 1
        else:
            correct_str = "/".join(correct_answers) if isinstance(q["Correct"], list) else q["Correct"]
            print(f"❌ Fout! Het juiste antwoord is {correct_str}")
    
    print(f"\n🎉 Je score: {score}/{len(questions)}")

# 🏁 3️⃣ Functie om categorie te selecteren
def select_category(questions):
    print("\n🎓 Selecteer een categorie:")
    print("1️⃣  Anatomy")
    print("2️⃣  Physics")
    print("0️⃣  Afsluiten")
    
    choice = input("\nJouw keuze (1/2/0): ").strip()
    
    if choice == "1":
        return [q for q in questions if q.get("Category") == "Anatomy"]
    elif choice == "2":
        return [q for q in questions if q.get("Category") == "Physics"]
    else:
        return None

# 🏁 4️⃣ Start van de quiz
def main():
    print("Welkom bij de MCQ Quiz!")
    
    while True:
        selected_questions = select_category(questions)
        
        if selected_questions is None:
            print("\n👋 Tot ziens!")
            break
        
        if not selected_questions:
            print("❌ Geen vragen beschikbaar in deze categorie.")
            continue
        
        take_quiz(selected_questions)

if __name__ == "__main__":
    main()