import unicodedata
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


FACTURACION_PATH = Path("tablas/facturacion_ventas.csv")
EGRESOS_PATH = Path("tablas/egresos.csv")
TODOS = "Todos"

MESES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}


st.set_page_config(
    page_title="Estados financieros",
    page_icon="📈",
    layout="wide",
)

st.title("Estados financieros")


def normalizar_texto(valor):
    texto = str(valor).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(letra for letra in texto if not unicodedata.combining(letra))
    return " ".join(texto.split())


def obtener_columna(df, nombre):
    objetivo = normalizar_texto(nombre)
    columnas = {normalizar_texto(columna): columna for columna in df.columns}
    if objetivo not in columnas:
        raise KeyError(f"No existe la columna requerida: {nombre}")
    return columnas[objetivo]


def limpiar_numero(valor):
    texto = str(valor).strip()

    if texto == "":
        return 0

    texto = texto.replace("$", "").replace(" ", "")

    # Soporta valores tipo 1.000.000, 1000000, 54000.0 y 4726207,95.
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        partes = texto.split(",")
        if len(partes[-1]) in [1, 2] and partes[-1].isdigit():
            texto = "".join(partes[:-1]).replace(".", "") + "." + partes[-1]
        else:
            texto = "".join(partes)
    elif "." in texto:
        partes = texto.split(".")
        if (
            len(partes) == 2
            and partes[-1].isdigit()
            and len(partes[0]) > 3
        ):
            texto = partes[0] + "." + partes[-1]
        else:
            texto = "".join(partes)

    return pd.to_numeric(texto, errors="coerce")


def preparar_fecha(df, columna_anio, columna_mes, columna_dia):
    df = df.copy()
    col_anio = obtener_columna(df, columna_anio)
    col_mes = obtener_columna(df, columna_mes)
    col_dia = obtener_columna(df, columna_dia)

    df["anio_norm"] = pd.to_numeric(df[col_anio], errors="coerce")
    df["mes_norm"] = pd.to_numeric(df[col_mes], errors="coerce")
    df["dia_norm"] = pd.to_numeric(df[col_dia], errors="coerce")

    df = df[
        df["anio_norm"].notna()
        & df["mes_norm"].notna()
        & df["dia_norm"].notna()
    ].copy()

    df["anio_norm"] = df["anio_norm"].astype(int)
    df["mes_norm"] = df["mes_norm"].astype(int)
    df["dia_norm"] = df["dia_norm"].astype(int)

    df["fecha_dt"] = pd.to_datetime(
        {
            "year": df["anio_norm"],
            "month": df["mes_norm"],
            "day": df["dia_norm"],
        },
        errors="coerce",
    )

    df = df[df["fecha_dt"].notna()].copy()
    df["periodo"] = df["fecha_dt"].dt.to_period("M").dt.to_timestamp()
    df["mes_nombre"] = df["mes_norm"].map(MESES)

    return df


@st.cache_data
def cargar_ingresos(mtime_archivo):
    df = pd.read_csv(
        FACTURACION_PATH,
        sep=";",
        dtype=str,
        keep_default_na=False,
    )
    df.columns = df.columns.str.strip()

    df = preparar_fecha(
        df,
        columna_anio="Año",
        columna_mes="Mes",
        columna_dia="Día",
    )

    columnas_ingreso = [
        "total efectivo",
        "total tarjeta",
        "total transfencia",
    ]

    for nombre_columna in columnas_ingreso:
        columna_real = obtener_columna(df, nombre_columna)
        df[columna_real] = df[columna_real].map(limpiar_numero).fillna(0)

    df["ingresos"] = sum(
        df[obtener_columna(df, nombre_columna)]
        for nombre_columna in columnas_ingreso
    )

    return df


@st.cache_data
def cargar_egresos(mtime_archivo):
    df = pd.read_csv(
        EGRESOS_PATH,
        sep=";",
        dtype=str,
        keep_default_na=False,
    )
    df.columns = df.columns.str.strip()

    df = preparar_fecha(
        df,
        columna_anio="año",
        columna_mes="mes",
        columna_dia="día",
    )

    columna_valor = obtener_columna(df, "Valor")
    df["valor"] = df[columna_valor].map(limpiar_numero).fillna(0)
    df["egresos"] = df["valor"]

    return df


def opciones_con_todos(valores):
    opciones = (
        pd.Series(valores)
        .dropna()
        .astype(int)
        .sort_values()
        .unique()
        .tolist()
    )
    return [TODOS] + opciones


def formatear_pesos(valor):
    return f"${valor:,.0f}"


df_ingresos = cargar_ingresos(FACTURACION_PATH.stat().st_mtime_ns)
df_egresos = cargar_egresos(EGRESOS_PATH.stat().st_mtime_ns)

anios_disponibles = sorted(
    set(df_ingresos["anio_norm"].unique().tolist())
    | set(df_egresos["anio_norm"].unique().tolist())
)
anios_con_ingresos = sorted(df_ingresos["anio_norm"].unique().tolist())
anio_maximo = max(anios_con_ingresos) if anios_con_ingresos else TODOS

st.header("Filtros")

col1, col2 = st.columns(2)

with col1:
    anios = st.multiselect(
        "Año",
        opciones_con_todos(anios_disponibles),
        default=[anio_maximo],
        key="finanzas_anio",
    )

with col2:
    mes_comparativo = st.selectbox(
        "Mes para comparar ingresos entre años",
        [TODOS] + list(MESES.keys()),
        format_func=lambda valor: (
            "Todos" if valor == TODOS else MESES.get(valor, str(valor))
        ),
        key="finanzas_mes_comparativo",
    )

if TODOS not in anios:
    df_ingresos_filtrado = df_ingresos[
        df_ingresos["anio_norm"].isin(anios)
    ].copy()
    df_egresos_filtrado = df_egresos[
        df_egresos["anio_norm"].isin(anios)
    ].copy()
else:
    df_ingresos_filtrado = df_ingresos.copy()
    df_egresos_filtrado = df_egresos.copy()

st.divider()

ingresos_mensuales = (
    df_ingresos_filtrado
    .groupby(["periodo", "anio_norm", "mes_norm", "mes_nombre"], as_index=False)
    .agg(ingresos=("ingresos", "sum"))
)

egresos_mensuales = (
    df_egresos_filtrado
    .groupby(["periodo", "anio_norm", "mes_norm", "mes_nombre"], as_index=False)
    .agg(egresos=("egresos", "sum"))
)

estado_resultados = pd.merge(
    ingresos_mensuales,
    egresos_mensuales,
    on=["periodo", "anio_norm", "mes_norm", "mes_nombre"],
    how="outer",
).fillna(0)

estado_resultados["utilidad"] = (
    estado_resultados["ingresos"] - estado_resultados["egresos"]
)
estado_resultados["margen"] = estado_resultados.apply(
    lambda fila: fila["utilidad"] / fila["ingresos"]
    if fila["ingresos"]
    else 0,
    axis=1,
)
estado_resultados = estado_resultados.sort_values("periodo")
estado_resultados["ingresos acumulados"] = (
    estado_resultados
    .groupby("anio_norm")["ingresos"]
    .cumsum()
)
estado_resultados["utilidad acumulada"] = (
    estado_resultados
    .groupby("anio_norm")["utilidad"]
    .cumsum()
)

if estado_resultados.empty:
    st.warning("No hay datos para los filtros seleccionados.")
    st.stop()

total_ingresos = estado_resultados["ingresos"].sum()
total_egresos = estado_resultados["egresos"].sum()
utilidad_total = estado_resultados["utilidad"].sum()
margen_total = utilidad_total / total_ingresos if total_ingresos else 0

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Ingresos", formatear_pesos(total_ingresos))

with col2:
    st.metric("Egresos", formatear_pesos(total_egresos))

with col3:
    st.metric("Utilidad", formatear_pesos(utilidad_total))

with col4:
    st.metric("Margen", f"{margen_total:.1%}")

st.divider()

st.subheader("Resultado mensual")

grafica_mensual = estado_resultados[
    ["periodo", "ingresos", "egresos", "utilidad"]
].copy()
grafica_mensual["periodo"] = grafica_mensual["periodo"].dt.strftime("%Y-%m")
grafica_mensual = grafica_mensual.melt(
    id_vars="periodo",
    value_vars=["ingresos", "egresos", "utilidad"],
    var_name="concepto",
    value_name="valor",
)

grafica_barras = (
    alt.Chart(grafica_mensual)
    .mark_bar()
    .encode(
        x=alt.X("periodo:N", title="Periodo"),
        xOffset=alt.XOffset("concepto:N"),
        y=alt.Y("valor:Q", title="Valor"),
        color=alt.Color("concepto:N", title="Concepto"),
        tooltip=[
            alt.Tooltip("periodo:N", title="Periodo"),
            alt.Tooltip("concepto:N", title="Concepto"),
            alt.Tooltip("valor:Q", title="Valor", format=",.0f"),
        ],
    )
    .properties(height=420)
)

st.altair_chart(grafica_barras, use_container_width=True)

st.subheader("Ventas 2026 vs meta mensual")

ingresos_por_mes_base = (
    df_ingresos
    .groupby(["anio_norm", "mes_norm", "mes_nombre"], as_index=False)
    .agg(ingresos=("ingresos", "sum"))
)

ventas_2026 = ingresos_por_mes_base[
    ingresos_por_mes_base["anio_norm"] == 2026
][["mes_norm", "mes_nombre", "ingresos"]].rename(
    columns={"ingresos": "ventas 2026"}
)

meta_2026 = ingresos_por_mes_base[
    ingresos_por_mes_base["anio_norm"] == 2025
][["mes_norm", "ingresos"]].rename(
    columns={"ingresos": "meta"}
)
meta_2026["meta"] = meta_2026["meta"] * 1.15

ventas_vs_meta = pd.merge(
    ventas_2026,
    meta_2026,
    on="mes_norm",
    how="outer",
).fillna(0)

ventas_vs_meta["mes_nombre"] = ventas_vs_meta["mes_norm"].map(MESES)
ventas_vs_meta["cumplimiento"] = ventas_vs_meta.apply(
    lambda fila: fila["ventas 2026"] / fila["meta"]
    if fila["meta"]
    else 0,
    axis=1,
)
ventas_vs_meta = ventas_vs_meta.sort_values("mes_norm")

if ventas_vs_meta.empty:
    st.info("No hay datos suficientes de 2025 y 2026 para calcular la meta.")
else:
    ventas_vs_meta_grafica = ventas_vs_meta.melt(
        id_vars=["mes_norm", "mes_nombre", "cumplimiento"],
        value_vars=["ventas 2026", "meta"],
        var_name="concepto",
        value_name="valor",
    )

    grafica_ventas_meta = (
        alt.Chart(ventas_vs_meta_grafica)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X(
                "mes_nombre:N",
                title="Mes",
                sort=[
                    MESES[mes]
                    for mes in range(1, 13)
                ],
            ),
            xOffset=alt.XOffset("concepto:N"),
            y=alt.Y("valor:Q", title="Valor"),
            color=alt.Color(
                "concepto:N",
                title="Concepto",
                scale=alt.Scale(
                    domain=["ventas 2026", "meta"],
                    range=["#2563eb", "#f59e0b"],
                ),
            ),
            tooltip=[
                alt.Tooltip("mes_nombre:N", title="Mes"),
                alt.Tooltip("concepto:N", title="Concepto"),
                alt.Tooltip("valor:Q", title="Valor", format=",.0f"),
                alt.Tooltip(
                    "cumplimiento:Q",
                    title="Cumplimiento",
                    format=".1%",
                ),
            ],
        )
        .properties(height=380)
    )

    st.altair_chart(grafica_ventas_meta, use_container_width=True)

    tabla_ventas_vs_meta = ventas_vs_meta.copy()
    tabla_ventas_vs_meta["cumplimiento"] = (
        tabla_ventas_vs_meta["cumplimiento"] * 100
    )

    st.dataframe(
        tabla_ventas_vs_meta[
            [
                "mes_nombre",
                "ventas 2026",
                "meta",
                "cumplimiento",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "mes_nombre": "Mes",
            "ventas 2026": st.column_config.NumberColumn(
                "Ventas 2026",
                format="$%d",
            ),
            "meta": st.column_config.NumberColumn(
                "Meta 2026",
                format="$%d",
            ),
            "cumplimiento": st.column_config.NumberColumn(
                "Cumplimiento",
                format="%.1f%%",
            ),
        },
    )

st.subheader("Utilidad acumulada mes a mes")

grafica_utilidad_acumulada = estado_resultados[
    ["periodo", "anio_norm", "utilidad acumulada"]
].copy()
grafica_utilidad_acumulada["periodo"] = (
    grafica_utilidad_acumulada["periodo"].dt.strftime("%Y-%m")
)

max_utilidad_acumulada = grafica_utilidad_acumulada[
    "utilidad acumulada"
].max()
umbral_amarillo = max(max_utilidad_acumulada * 0.15, 1)

grafica_utilidad_acumulada["semaforo"] = pd.cut(
    grafica_utilidad_acumulada["utilidad acumulada"],
    bins=[float("-inf"), -1, umbral_amarillo, float("inf")],
    labels=["Rojo", "Amarillo", "Verde"],
)

base_utilidad_acumulada = alt.Chart(grafica_utilidad_acumulada).encode(
    x=alt.X(
        "periodo:N",
        title="Periodo",
        axis=alt.Axis(labelAngle=-35),
    ),
    y=alt.Y(
        "utilidad acumulada:Q",
        title="Utilidad acumulada",
    ),
    color=alt.Color(
        "semaforo:N",
        title="Estado",
        scale=alt.Scale(
            domain=["Rojo", "Amarillo", "Verde"],
            range=["#dc2626", "#ca8a04", "#16a34a"],
        ),
    ),
    tooltip=[
        alt.Tooltip("periodo:N", title="Periodo"),
        alt.Tooltip("anio_norm:N", title="Año"),
        alt.Tooltip("semaforo:N", title="Estado"),
        alt.Tooltip(
            "utilidad acumulada:Q",
            title="Utilidad acumulada",
            format=",.0f",
        ),
    ],
)

area_utilidad = base_utilidad_acumulada.mark_area(
    opacity=0.22,
    interpolate="monotone",
)

linea_utilidad = base_utilidad_acumulada.mark_line(
    strokeWidth=3,
    interpolate="monotone",
)

puntos_utilidad = base_utilidad_acumulada.mark_circle(
    size=72,
    opacity=0.95,
    stroke="#ffffff",
    strokeWidth=1.5,
)

linea_cero = (
    alt.Chart(pd.DataFrame({"cero": [0]}))
    .mark_rule(color="#525252", strokeDash=[6, 4], opacity=0.75)
    .encode(y="cero:Q")
)

grafica_utilidad_acumulada_altair = (
    area_utilidad + linea_utilidad + puntos_utilidad + linea_cero
).properties(
    height=390,
)

st.altair_chart(grafica_utilidad_acumulada_altair, use_container_width=True)

st.subheader("Estado de resultados mensual")

tabla_resultados = estado_resultados.copy()
tabla_resultados["periodo"] = tabla_resultados["periodo"].dt.strftime("%Y-%m")
tabla_resultados["margen"] = tabla_resultados["margen"] * 100
tabla_resultados = tabla_resultados[
    [
        "periodo",
        "anio_norm",
        "mes_norm",
        "mes_nombre",
        "ingresos",
        "ingresos acumulados",
        "egresos",
        "utilidad",
        "utilidad acumulada",
        "margen",
    ]
]

st.dataframe(
    tabla_resultados,
    use_container_width=True,
    hide_index=True,
    column_config={
        "periodo": "Periodo",
        "anio_norm": "Año",
        "mes_norm": "Mes",
        "mes_nombre": "Mes nombre",
        "ingresos": st.column_config.NumberColumn("Ingresos", format="$%d"),
        "ingresos acumulados": st.column_config.NumberColumn(
            "Ingresos acumulados",
            format="$%d",
        ),
        "egresos": st.column_config.NumberColumn("Egresos", format="$%d"),
        "utilidad": st.column_config.NumberColumn("Utilidad", format="$%d"),
        "utilidad acumulada": st.column_config.NumberColumn(
            "Utilidad acumulada",
            format="$%d",
        ),
        "margen": st.column_config.NumberColumn("Margen", format="%.1f%%"),
    },
)

st.divider()

st.subheader("Comparativo de ingresos por mes entre años")

comparativo_ingresos = (
    df_ingresos
    .groupby(["anio_norm", "mes_norm", "mes_nombre"], as_index=False)
    .agg(ingresos=("ingresos", "sum"))
)

if mes_comparativo != TODOS:
    comparativo_ingresos = comparativo_ingresos[
        comparativo_ingresos["mes_norm"] == mes_comparativo
    ]

if comparativo_ingresos.empty:
    st.info("No hay ingresos para comparar con ese mes.")
else:
    comparativo_tabla = comparativo_ingresos.pivot_table(
        index="mes_nombre",
        columns="anio_norm",
        values="ingresos",
        aggfunc="sum",
        fill_value=0,
    )

    orden_meses = [
        MESES[mes]
        for mes in range(1, 13)
        if MESES[mes] in comparativo_tabla.index
    ]
    comparativo_tabla = comparativo_tabla.loc[orden_meses]

    st.bar_chart(comparativo_tabla)
    st.dataframe(comparativo_tabla, use_container_width=True)

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Egresos por grupo")

    if "Grupo 1" in df_egresos_filtrado.columns:
        egresos_grupo = (
            df_egresos_filtrado
            .groupby("Grupo 1", as_index=False)
            .agg(egresos=("egresos", "sum"))
            .sort_values("egresos", ascending=False)
        )

        st.bar_chart(egresos_grupo.set_index("Grupo 1")["egresos"])
        st.dataframe(
            egresos_grupo,
            use_container_width=True,
            hide_index=True,
            column_config={
                "egresos": st.column_config.NumberColumn(
                    "Egresos",
                    format="$%d",
                )
            },
        )
    else:
        st.info("No existe la columna Grupo 1 en egresos.csv.")

with col2:
    st.subheader("Egresos por tipo")

    if "Tipo de Egreso" in df_egresos_filtrado.columns:
        egresos_tipo = (
            df_egresos_filtrado
            .groupby("Tipo de Egreso", as_index=False)
            .agg(egresos=("egresos", "sum"))
            .sort_values("egresos", ascending=False)
            .head(15)
        )

        st.bar_chart(egresos_tipo.set_index("Tipo de Egreso")["egresos"])
        st.dataframe(
            egresos_tipo,
            use_container_width=True,
            hide_index=True,
            column_config={
                "egresos": st.column_config.NumberColumn(
                    "Egresos",
                    format="$%d",
                )
            },
        )
    else:
        st.info("No existe la columna Tipo de Egreso en egresos.csv.")
