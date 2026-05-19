from datetime import date

def calcular_metrica(nome, ano):
    if nome == "data_hoje":
        return str(ano)   # mostra o ano selecionado, não a data atual
    return "—"
