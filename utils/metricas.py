from datetime import date

def calcular_metrica(nome, ano):
    if nome == "data_hoje":
        return date.today().strftime("%d/%m/%Y")
    return "—"
