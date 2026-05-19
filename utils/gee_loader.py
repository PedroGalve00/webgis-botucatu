import ee
import pandas as pd

CODIGO_BOTUCATU = 3507506

# Legenda oficial MapBiomas Collection 9
MAPBIOMAS_CLASSES = {
    1:  {"nome": "Floresta Amazônica",       "cor": "#1f8d49"},
    3:  {"nome": "Formação Florestal",        "cor": "#1f8d49"},
    4:  {"nome": "Formação Savânica",         "cor": "#7dc975"},
    5:  {"nome": "Mangue",                   "cor": "#04381d"},
    6:  {"nome": "Floresta Alagável",         "cor": "#026975"},
    11: {"nome": "Campo Alagado",             "cor": "#519799"},
    12: {"nome": "Formação Campestre",        "cor": "#d6bc74"},
    13: {"nome": "Outra Formação não Florestal", "cor": "#d89f5c"},
    15: {"nome": "Pastagem",                  "cor": "#edde8e"},
    18: {"nome": "Agricultura",               "cor": "#E974ED"},
    19: {"nome": "Lavoura Temporária",        "cor": "#C27BA0"},
    20: {"nome": "Cana",                      "cor": "#db7093"},
    21: {"nome": "Mosaico Agricultura/Pasto", "cor": "#ffa07a"},
    22: {"nome": "Área não Vegetada",         "cor": "#d4271e"},
    23: {"nome": "Praia e Duna",              "cor": "#ffa500"},
    24: {"nome": "Área Urbanizada",           "cor": "#d4271e"},
    25: {"nome": "Outras Áreas não Veg.",     "cor": "#db4d4f"},
    29: {"nome": "Afloramento Rochoso",       "cor": "#ffaa5f"},
    30: {"nome": "Mineração",                 "cor": "#9c0027"},
    31: {"nome": "Aquicultura",               "cor": "#091077"},
    32: {"nome": "Apicum",                    "cor": "#fc8114"},
    33: {"nome": "Rio/Lago/Oceano",           "cor": "#2532e4"},
    36: {"nome": "Lavoura Perene",            "cor": "#7a5900"},
    39: {"nome": "Soja",                      "cor": "#f5b3c8"},
    40: {"nome": "Arroz",                     "cor": "#c71585"},
    41: {"nome": "Outras Lavouras Temp.",     "cor": "#f54ca9"},
    46: {"nome": "Café",                      "cor": "#d68fe2"},
    47: {"nome": "Citrus",                    "cor": "#9932cc"},
    48: {"nome": "Outras Lavouras Per.",      "cor": "#e6ccff"},
    49: {"nome": "Restinga Arbórea",          "cor": "#02d659"},
    50: {"nome": "Restinga Herbácea",         "cor": "#ad5100"},
    62: {"nome": "Algodão",                   "cor": "#ff69b4"},
}

def get_botucatu():
    municipios = ee.FeatureCollection("projects/mapbiomas-workspace/AUXILIAR/municipios-2016")
    return municipios.filter(ee.Filter.eq("CD_GEOCMU", str(CODIGO_BOTUCATU))).geometry()

def calcular_indice(image, indice):
    if indice == "NDVI":
        return image.normalizedDifference(["B8", "B4"]).rename("NDVI")
    elif indice == "EVI":
        return image.expression(
            "2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))",
            {"NIR": image.select("B8"), "RED": image.select("B4"), "BLUE": image.select("B2")}
        ).rename("EVI")
    elif indice == "NDWI":
        return image.normalizedDifference(["B3", "B8"]).rename("NDWI")
    elif indice == "LST":
        return image.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15).rename("LST")
    else:
        return image.select(0)

def carregar_camada(config_camada, ano):
    try:
        tipo    = config_camada.get("tipo", "colecao")
        id_gee  = config_camada["id_gee"]
        palette = config_camada.get("palette", [])
        vmin    = str(config_camada.get("min", 0))
        vmax    = str(config_camada.get("max", 1))
        vis     = {"min": vmin, "max": vmax, "palette": ",".join(palette)}
        regiao  = get_botucatu()

        if tipo == "mapbiomas":
            ano_uso = min(ano, config_camada.get("ano_max", 2023))
            banda   = f"classification_{ano_uso}"
            image   = ee.Image(id_gee).select(banda).clip(regiao)

        elif tipo == "asset":
            banda = config_camada.get("banda")
            image = ee.Image(id_gee)
            if banda:
                image = image.select(banda).clip(regiao)

        elif tipo == "indice":
            indice = config_camada.get("indice", "NDVI")
            image = (
                ee.ImageCollection(id_gee)
                .filterDate(f"{ano}-01-01", f"{ano}-12-31")
                .filterBounds(regiao)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
                .map(lambda img: calcular_indice(img, indice))
                .median()
                .clip(regiao)
            )

        elif tipo == "colecao":
            bandas = config_camada.get("bandas", ["B4", "B3", "B2"])
            image = (
                ee.ImageCollection(id_gee)
                .filterDate(f"{ano}-01-01", f"{ano}-12-31")
                .filterBounds(regiao)
                .median()
                .select(bandas)
                .clip(regiao)
            )
            vis = {"bands": bandas, "min": vmin, "max": vmax}

        return image, vis

    except Exception as e:
        print(f"Erro ao carregar camada: {e}")
        return None, {}

def calcular_serie_temporal(config_camada, ano_inicio, ano_fim, lat, lon):
    try:
        tipo   = config_camada.get("tipo")
        id_gee = config_camada["id_gee"]
        indice = config_camada.get("indice")
        regiao = get_botucatu()

        if tipo == "mapbiomas":
            # Calcula área (ha) por classe por ano
            registros = []
            ano_max = config_camada.get("ano_max", 2023)
            for ano in range(ano_inicio, min(ano_fim, ano_max) + 1):
                try:
                    banda = f"classification_{ano}"
                    image = ee.Image(id_gee).select(banda).clip(regiao)

                    # Conta pixels por classe (pixel = 30x30m = 0.09ha)
                    freq = image.reduceRegion(
                        reducer=ee.Reducer.frequencyHistogram(),
                        geometry=regiao,
                        scale=30,
                        maxPixels=1e9,
                    ).getInfo()

                    hist = list(freq.values())[0] if freq else {}
                    for classe_str, pixels in hist.items():
                        classe = int(float(classe_str))
                        if classe in MAPBIOMAS_CLASSES:
                            area_ha = round(pixels * 0.09, 1)
                            registros.append({
                                "ano": ano,
                                "classe": MAPBIOMAS_CLASSES[classe]["nome"],
                                "cor": MAPBIOMAS_CLASSES[classe]["cor"],
                                "area_ha": area_ha,
                            })
                except:
                    continue

            return pd.DataFrame(registros) if registros else None

        elif tipo == "asset":
            return None

        else:
            registros = []
            for ano in range(ano_inicio, ano_fim + 1):
                try:
                    col = (
                        ee.ImageCollection(id_gee)
                        .filterDate(f"{ano}-01-01", f"{ano}-12-31")
                        .filterBounds(regiao)
                        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
                    )
                    if indice:
                        col = col.map(lambda img: calcular_indice(img, indice))
                    stats = col.median().reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=regiao,
                        scale=1000,
                        maxPixels=1e9,
                    ).getInfo()
                    valor = next((v for v in stats.values() if v is not None), None)
                    if valor is not None:
                        registros.append({"ano": ano, "valor": round(valor, 4)})
                except:
                    continue

            return pd.DataFrame(registros) if registros else None

    except Exception as e:
        print(f"Erro na série temporal: {e}")
        return None
