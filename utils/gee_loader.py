import ee
import pandas as pd

# Código IBGE de Botucatu
CODIGO_BOTUCATU = 3507506

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
            registros = []
            ano_max = config_camada.get("ano_max", 2023)
            for ano in range(ano_inicio, min(ano_fim, ano_max) + 1):
                try:
                    banda = f"classification_{ano}"
                    image = ee.Image(id_gee).select(banda).clip(regiao)

                    total = image.unmask(0).gt(0).reduceRegion(
                        reducer=ee.Reducer.sum(),
                        geometry=regiao,
                        scale=30,
                        maxPixels=1e9,
                    ).getInfo()

                    veg = image.remap(
                        [1, 3, 4, 5, 11, 12, 13],
                        [1, 1, 1,  1,  1,  1,  1],
                        0
                    ).reduceRegion(
                        reducer=ee.Reducer.sum(),
                        geometry=regiao,
                        scale=30,
                        maxPixels=1e9,
                    ).getInfo()

                    t = list(total.values())[0] or 1
                    v = list(veg.values())[0] or 0
                    perc = round((v / t) * 100, 1)
                    registros.append({"ano": ano, "valor": perc})

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
