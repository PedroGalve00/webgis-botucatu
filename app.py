import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
import geopandas as gpd
import os
from datetime import date
from config import PROJETO
from utils.gee_loader import carregar_camada, calcular_serie_temporal
from utils.metricas import calcular_metrica

st.set_page_config(page_title=PROJETO["nome"], page_icon="🌿", layout="wide")

cor = PROJETO["cor_primaria"]
st.markdown(f"""
<style>
    .titulo {{ color:{cor}; font-size:1.5rem; font-weight:700;
               border-left:4px solid {cor}; padding-left:12px; }}
    .card {{ background:white; border-radius:10px; padding:16px;
             border-top:3px solid {cor}; box-shadow:0 1px 4px rgba(0,0,0,0.08); }}
    .valor {{ font-size:1.8rem; font-weight:700; color:{cor}; }}
    .label {{ font-size:0.78rem; color:#666; }}
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_gee():
    try:
        if "GEE_SERVICE_ACCOUNT" in st.secrets:
            creds = ee.ServiceAccountCredentials(
                st.secrets["GEE_SERVICE_ACCOUNT"],
                key_data=st.secrets["GEE_PRIVATE_KEY"]
            )
            ee.Initialize(creds)
        else:
            ee.Initialize(project="pedrogalve")
    except Exception as e:
        st.error(f"Erro GEE: {e}")
        st.stop()

init_gee()

with st.sidebar:
    if os.path.exists(PROJETO["logo"]):
        st.image(PROJETO["logo"], width=160)
    st.markdown(f"**{PROJETO['cliente']}**")
    st.divider()
    ano = st.slider("Ano de análise", PROJETO["ano_inicio"], PROJETO["ano_fim"], PROJETO["ano_fim"])
    nomes = [c["nome"] for c in PROJETO["camadas"]]
    camada_sel = st.selectbox("Camada do mapa", nomes)
    cfg_camada = next(c for c in PROJETO["camadas"] if c["nome"] == camada_sel)
    if st.button("🔄 Atualizar dados"):
        st.cache_data.clear()
        st.rerun()

st.markdown(f'<p class="titulo">{PROJETO["nome"]}</p>', unsafe_allow_html=True)
st.caption(f"Ano: {ano}  ·  Dados de: {ano}")
st.markdown("")

cols = st.columns(len(PROJETO["metricas"]))
for i, m in enumerate(PROJETO["metricas"]):
    v = f'{m["valor_fixo"]:,}'.replace(",", ".") if "valor_fixo" in m else calcular_metrica(m["calcular"], ano)
    with cols[i]:
        st.markdown(f'<div class="card"><div class="valor">{v}</div><div class="label">{m["label"]}</div></div>', unsafe_allow_html=True)

st.markdown("")
col_mapa, col_graf = st.columns([3, 2])

with col_mapa:
    st.markdown(f"##### 🗺 {camada_sel} — {ano}")

    @st.cache_data(ttl=PROJETO["cache_horas"] * 3600)
    def get_tile_url(nome, ano):
        cfg = next(c for c in PROJETO["camadas"] if c["nome"] == nome)
        image, vis = carregar_camada(cfg, ano)
        if image is None:
            return None
        map_id = image.getMapId(vis)
        return map_id["tile_fetcher"].url_format

    with st.spinner("Carregando GEE..."):
        tile_url = get_tile_url(camada_sel, ano)
        m = folium.Map(
            location=[PROJETO["centro_lat"], PROJETO["centro_lon"]],
            zoom_start=PROJETO["zoom_inicial"],
            tiles="CartoDB positron"
        )
        if tile_url:
            folium.TileLayer(
                tiles=tile_url,
                attr="Google Earth Engine",
                name=camada_sel,
                overlay=True,
            ).add_to(m)
        if os.path.exists(PROJETO["geojson_area"]):
            gdf = gpd.read_file(PROJETO["geojson_area"])
            folium.GeoJson(
                gdf, name="Área de estudo",
                style_function=lambda x: {"color": cor, "fillOpacity": 0.05}
            ).add_to(m)
        folium.LayerControl().add_to(m)
        st_folium(m, height=460, use_container_width=True)

with col_graf:
    cfg_atual = next(c for c in PROJETO["camadas"] if c["nome"] == camada_sel)
    eh_mapbiomas = cfg_atual.get("tipo") == "mapbiomas"

    st.markdown("##### 📊 Uso do solo por ano (ha)" if eh_mapbiomas else "##### 📈 Série temporal")

    @st.cache_data(ttl=PROJETO["cache_horas"] * 3600)
    def get_serie(nome):
        cfg = next(c for c in PROJETO["camadas"] if c["nome"] == nome)
        return calcular_serie_temporal(
            cfg,
            PROJETO["ano_inicio"], PROJETO["ano_fim"],
            PROJETO["centro_lat"], PROJETO["centro_lon"]
        )

    with st.spinner("Calculando... (pode levar 1-2 min na primeira vez)"):
        df = get_serie(camada_sel)

    if df is not None and not df.empty:
        if eh_mapbiomas:
            # Gráfico de área empilhada com cores oficiais MapBiomas
            classes = df["classe"].unique()
            cores   = {row["classe"]: row["cor"] for _, row in df.drop_duplicates("classe").iterrows()}

            # Filtra as 8 maiores classes para não poluir o gráfico
            top_classes = (
                df.groupby("classe")["area_ha"].mean()
                .sort_values(ascending=False)
                .head(8).index.tolist()
            )
            df_top = df[df["classe"].isin(top_classes)]

            fig = px.bar(
                df_top, x="ano", y="area_ha",
                color="classe",
                color_discrete_map=cores,
                labels={"ano": "Ano", "area_ha": "Área (ha)", "classe": "Classe"},
                barmode="stack",
            )
            fig.update_layout(
                plot_bgcolor="white", paper_bgcolor="white",
                margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(font=dict(size=10), orientation="v"),
                xaxis=dict(tickmode="linear"),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Tabela do ano selecionado
            ano_disp = min(ano, cfg_atual.get("ano_max", 2023))
            df_ano = df[df["ano"] == ano_disp][["classe","area_ha"]].sort_values("area_ha", ascending=False)
            df_ano.columns = ["Classe", "Área (ha)"]
            st.caption(f"Detalhamento — {ano_disp}")
            st.dataframe(df_ano, use_container_width=True, hide_index=True)

        else:
            fig = px.line(df, x="ano", y="valor", markers=True,
                          color_discrete_sequence=[cor],
                          labels={"ano": "Ano", "valor": camada_sel})
            fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                              margin=dict(l=10,r=10,t=10,b=10), showlegend=False)
            fig.add_vrect(x0=ano-.1, x1=ano+.1, fillcolor=cor, opacity=0.15, line_width=0)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df.rename(columns={"ano":"Ano","valor":camada_sel}),
                         use_container_width=True, hide_index=True)
    else:
        st.info("Calculando dados... aguarde e clique em Atualizar.")

st.divider()
st.caption(f"Dados: Google Earth Engine · MapBiomas · {PROJETO['cliente']} · {date.today().year}")
