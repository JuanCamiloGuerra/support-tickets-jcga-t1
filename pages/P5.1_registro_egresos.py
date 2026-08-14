from datetime import date
from pathlib import Path
import unicodedata

import pandas as pd
import streamlit as st


EGRESOS_PATH = Path("tablas/egresos.csv")
GRUPOS_EGRESOS_PATH = Path("tablas/grupos_egresos.csv")


st.set_page_config(
    page_title="Registro de egresos",
    page_icon="💸",
    layout="wide",
)

st.title("Registro de egresos")


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


def formatear_pesos(valor):
    return f"${int(valor):,}".replace(",", ".")


def limpiar_pesos(valor):
    texto = str(valor).strip()

    if texto == "":
        return 0

    texto = texto.replace("$", "").replace(" ", "")

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

    numero = pd.to_numeric(texto, errors="coerce")
    return int(round(numero)) if pd.notna(numero) else 0


def convertir_fecha(valor):
    fecha = pd.to_datetime(str(valor), dayfirst=True, errors="coerce")

    if pd.isna(fecha):
        return date.today()

    return fecha.date()


@st.cache_data
def cargar_egresos():
    return pd.read_csv(
        EGRESOS_PATH,
        sep=";",
        dtype=str,
        keep_default_na=False,
    )


@st.cache_data
def cargar_grupos_egresos():
    df = pd.read_csv(
        GRUPOS_EGRESOS_PATH,
        sep=";",
        dtype=str,
        keep_default_na=False,
    )
    df.columns = df.columns.str.strip()
    return df


df_egresos = cargar_egresos()
df_grupos = cargar_grupos_egresos()

col_grupo_1 = obtener_columna(df_grupos, "Grupo 1")
col_grupo_3 = obtener_columna(df_grupos, "Grupo 3")

df_tipos_egreso = (
    df_grupos[[col_grupo_1, col_grupo_3]]
    .copy()
)
df_tipos_egreso[col_grupo_1] = df_tipos_egreso[col_grupo_1].str.strip()
df_tipos_egreso[col_grupo_3] = df_tipos_egreso[col_grupo_3].str.strip()
df_tipos_egreso = df_tipos_egreso[
    df_tipos_egreso[col_grupo_3] != ""
].drop_duplicates(subset=[col_grupo_3])

tipos_egreso = sorted(df_tipos_egreso[col_grupo_3].tolist())

mapa_grupo_1 = dict(
    zip(
        df_tipos_egreso[col_grupo_3],
        df_tipos_egreso[col_grupo_1],
    )
)

st.header("Nuevo egreso")

fecha_base = date.today()

col1, col2 = st.columns(2)

with col1:
    tipo_egreso = st.selectbox(
        "Tipo de Egreso",
        tipos_egreso,
        key="tipo_egreso_egresos",
    )

grupo_1 = mapa_grupo_1.get(tipo_egreso, "")

with col2:
    st.text_input(
        "Grupo 1",
        value=grupo_1,
        disabled=True,
        key="grupo_1_egresos",
    )

with st.form("formulario_registro_egresos", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)

    with col1:
        dia = st.number_input(
            "Día",
            min_value=1,
            max_value=31,
            value=fecha_base.day,
            step=1,
        )

    with col2:
        mes = st.number_input(
            "Mes",
            min_value=1,
            max_value=12,
            value=fecha_base.month,
            step=1,
        )

    with col3:
        anio = st.number_input(
            "Año",
            min_value=2020,
            max_value=2100,
            value=fecha_base.year,
            step=1,
        )

    nota = st.text_area(
        "Nota-Observacion",
        height=90,
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        valor = st.number_input(
            "Valor",
            min_value=0,
            value=0,
            step=1000,
        )

    with col2:
        quien_paga = st.selectbox(
            "Quien paga",
            ["Juan", "Clelia", "Karol"],
        )

    with col3:
        de_donde_paga = st.selectbox(
            "De donde Paga",
            ["BANCOLOMBIA", "BBVA", "NEQUI", "EFECTIVO"],
        )

    with col4:
        actuals_fcst = st.selectbox(
            "Actuals / FCST",
            ["ACT", "FCST"],
        )

    registrar = st.form_submit_button(
        "Registrar egreso",
        use_container_width=True,
    )

if registrar:
    try:
        fecha = date(int(anio), int(mes), int(dia))
    except ValueError:
        st.error("La fecha seleccionada no es válida. Revisa día, mes y año.")
        st.stop()

    if valor <= 0:
        st.error("El valor del egreso debe ser mayor a cero.")
        st.stop()

    if not grupo_1:
        st.error("No se encontró Grupo 1 para el tipo de egreso seleccionado.")
        st.stop()

    columnas_egresos = df_egresos.columns.tolist()
    nueva_fila = {columna: "" for columna in columnas_egresos}
    nueva_fila[obtener_columna(df_egresos, "Fecha")] = (
        f"{fecha.day}/{fecha.month:02d}/{fecha.year}"
    )
    nueva_fila[obtener_columna(df_egresos, "año")] = str(fecha.year)
    nueva_fila[obtener_columna(df_egresos, "mes")] = str(fecha.month)
    nueva_fila[obtener_columna(df_egresos, "día")] = str(fecha.day)
    nueva_fila[obtener_columna(df_egresos, "Tipo de Egreso")] = tipo_egreso
    nueva_fila[obtener_columna(df_egresos, "Nota-Observacion")] = nota.strip()
    nueva_fila[obtener_columna(df_egresos, "Valor")] = formatear_pesos(valor)
    nueva_fila[obtener_columna(df_egresos, "Grupo 1")] = grupo_1
    nueva_fila[obtener_columna(df_egresos, "Quien paga")] = quien_paga
    nueva_fila[obtener_columna(df_egresos, "De donde Paga")] = de_donde_paga
    nueva_fila[obtener_columna(df_egresos, "Actuals / FCST")] = actuals_fcst

    df_nueva_fila = pd.DataFrame(
        [nueva_fila],
        columns=columnas_egresos,
    )

    df_nueva_fila.to_csv(
        EGRESOS_PATH,
        sep=";",
        mode="a",
        header=False,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    st.cache_data.clear()
    st.success("Egreso registrado correctamente.")

st.divider()

st.header("Últimos egresos registrados")

df_egresos_actualizado = cargar_egresos()

st.dataframe(
    df_egresos_actualizado.tail(10),
    use_container_width=True,
    hide_index=True,
)

st.divider()

st.header("Actualizar egresos FCST")

col_actuals = obtener_columna(df_egresos_actualizado, "Actuals / FCST")
col_fecha = obtener_columna(df_egresos_actualizado, "Fecha")
col_anio = obtener_columna(df_egresos_actualizado, "año")
col_mes = obtener_columna(df_egresos_actualizado, "mes")
col_dia = obtener_columna(df_egresos_actualizado, "día")
col_tipo = obtener_columna(df_egresos_actualizado, "Tipo de Egreso")
col_nota = obtener_columna(df_egresos_actualizado, "Nota-Observacion")
col_valor = obtener_columna(df_egresos_actualizado, "Valor")
col_quien_paga = obtener_columna(df_egresos_actualizado, "Quien paga")
col_de_donde_paga = obtener_columna(df_egresos_actualizado, "De donde Paga")

df_fcst = df_egresos_actualizado[
    df_egresos_actualizado[col_actuals].astype(str).str.strip().eq("FCST")
].copy()

if df_fcst.empty:
    st.info("No hay egresos FCST pendientes por actualizar.")
else:
    df_fcst["fila_csv"] = df_fcst.index
    df_fcst["descripcion"] = (
        "#"
        + df_fcst["fila_csv"].astype(str)
        + " | "
        + df_fcst[col_fecha].astype(str)
        + " | "
        + df_fcst[col_tipo].astype(str)
        + " | "
        + df_fcst[col_valor].astype(str)
        + " | "
        + df_fcst[col_nota].astype(str)
    )

    fila_seleccionada = st.selectbox(
        "Selecciona el egreso FCST a actualizar",
        df_fcst["fila_csv"].tolist(),
        format_func=lambda fila: df_fcst.loc[
            df_fcst["fila_csv"] == fila,
            "descripcion",
        ].iloc[0],
        key="egreso_fcst_a_editar",
    )

    fila_actual = df_egresos_actualizado.loc[fila_seleccionada]

    st.dataframe(
        pd.DataFrame([fila_actual]),
        use_container_width=True,
        hide_index=True,
    )

    with st.form("formulario_actualizar_fcst"):
        col1, col2, col3 = st.columns(3)

        with col1:
            nueva_fecha = st.date_input(
                "Fecha real",
                value=convertir_fecha(fila_actual[col_fecha]),
            )

        with col2:
            nuevo_valor = st.number_input(
                "Valor real",
                min_value=0,
                value=limpiar_pesos(fila_actual[col_valor]),
                step=1000,
            )

        with col3:
            nuevo_estado = st.selectbox(
                "Actuals / FCST",
                ["ACT", "FCST"],
                index=0,
            )

        col1, col2, col3 = st.columns(3)

        with col1:
            nuevo_quien_paga = st.selectbox(
                "Quien paga",
                ["Juan", "Clelia", "Karol"],
                index=["Juan", "Clelia", "Karol"].index(
                    fila_actual[col_quien_paga]
                )
                if fila_actual[col_quien_paga] in ["Juan", "Clelia", "Karol"]
                else 0,
            )

        with col2:
            nuevo_de_donde_paga = st.selectbox(
                "De donde Paga",
                ["BANCOLOMBIA", "BBVA", "NEQUI", "EFECTIVO"],
                index=["BANCOLOMBIA", "BBVA", "NEQUI", "EFECTIVO"].index(
                    fila_actual[col_de_donde_paga]
                )
                if fila_actual[col_de_donde_paga]
                in ["BANCOLOMBIA", "BBVA", "NEQUI", "EFECTIVO"]
                else 0,
            )

        with col3:
            st.text_input(
                "Tipo de Egreso",
                value=fila_actual[col_tipo],
                disabled=True,
            )

        nueva_nota = st.text_area(
            "Nota-Observacion",
            value=fila_actual[col_nota],
            height=90,
        )

        actualizar_fcst = st.form_submit_button(
            "Actualizar egreso seleccionado",
            use_container_width=True,
        )

    if actualizar_fcst:
        df_egresos_actualizado.loc[fila_seleccionada, col_fecha] = (
            f"{nueva_fecha.day}/{nueva_fecha.month:02d}/{nueva_fecha.year}"
        )
        df_egresos_actualizado.loc[fila_seleccionada, col_anio] = str(
            nueva_fecha.year
        )
        df_egresos_actualizado.loc[fila_seleccionada, col_mes] = str(
            nueva_fecha.month
        )
        df_egresos_actualizado.loc[fila_seleccionada, col_dia] = str(
            nueva_fecha.day
        )
        df_egresos_actualizado.loc[fila_seleccionada, col_valor] = (
            formatear_pesos(nuevo_valor)
        )
        df_egresos_actualizado.loc[fila_seleccionada, col_actuals] = nuevo_estado
        df_egresos_actualizado.loc[fila_seleccionada, col_quien_paga] = (
            nuevo_quien_paga
        )
        df_egresos_actualizado.loc[fila_seleccionada, col_de_donde_paga] = (
            nuevo_de_donde_paga
        )
        df_egresos_actualizado.loc[fila_seleccionada, col_nota] = (
            nueva_nota.strip()
        )

        df_egresos_actualizado.to_csv(
            EGRESOS_PATH,
            sep=";",
            index=False,
            encoding="utf-8",
            lineterminator="\n",
        )

        st.cache_data.clear()
        st.success("Egreso actualizado correctamente.")
        st.rerun()
