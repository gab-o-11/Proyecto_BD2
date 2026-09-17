from Tokens import KEYWORDS

for texto, token in KEYWORDS.items():
    if texto != token.name:
        print(f"ERROR: '{texto}' apunta a {token}")

print("Revisión terminada")