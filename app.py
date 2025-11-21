import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="Promoción Casino - App Unificada", layout="wide")
st.title("🎰 App Unificada - Promociones Casino")

# === SUBIDA DE ARCHIVOS ===
col1, col2 = st.columns(2)
with col1:
    archivo_jugado = st.file_uploader("📄 Subí archivo de jugado (CSV o Excel)", type=["csv", "xlsx"], key="jugado")
with col2:
    archivo_depositos = st.file_uploader("📄 Subí archivo de depósitos (CSV o Excel)", type=["csv", "xlsx"], key="depositos")

# === PARÁMETROS DE PROMOCIÓN ===
st.sidebar.header("⚙️ Configuración de la Promoción")
porcentaje_bono = st.sidebar.number_input("Porcentaje de bono a entregar (%)", min_value=0.0, step=1.0)
deposito_minimo = st.sidebar.number_input("Depósito mínimo requerido", min_value=0.0, step=100.0)
jugado_minimo = st.sidebar.number_input("Importe jugado mínimo requerido", min_value=0.0, step=100.0)
tope_bono = st.sidebar.number_input("Importe máximo de bono por usuario", min_value=0.0, step=100.0)
aplica_rollover = st.sidebar.checkbox("¿Aplicar rollover?")
if aplica_rollover:
    cant_rollover = st.sidebar.number_input("Cantidad de rollover requerido", min_value=1)
else:
    cant_rollover = None
tipo_deposito = st.sidebar.selectbox("Tipo de depósito a considerar", ["Suma de depósitos", "Depósito máximo", "Depósito mínimo"])

# === FUNCIONES ===
def procesar_jugado(archivo):
    ext = archivo.name.split(".")[-1]
    df = pd.read_excel(archivo) if ext == "xlsx" else pd.read_csv(archivo, sep=None, engine="python")
    usuario_col = next((col for col in df.columns if col.strip().lower() == 'usuario'), None)
    if not usuario_col:
        st.warning("⚠️ No se encontró la columna 'usuario'.")
        return None
    cols_montos = [col for col in df.columns if any(p in col.lower() for p in ["jugado", "ganado", "neto"])]
    for col in cols_montos:
        df[col] = pd.to_numeric(df[col], errors='coerce').abs()
    df["suma_total_jugado"] = df[[c for c in cols_montos if "jugado" in c.lower()]].sum(axis=1)
    resumen = df.groupby(usuario_col).agg(total_jugado=("suma_total_jugado", "sum")).reset_index()
    resumen = resumen[resumen["total_jugado"] > 0]
    resumen = resumen.rename(columns={usuario_col: "usuario"})
    return resumen

def procesar_depositos(archivo):
    ext = archivo.name.split(".")[-1]
    df = pd.read_excel(archivo) if ext == "xlsx" else pd.read_csv(archivo, sep=None, engine="python")

    # Detectar columna 'beneficiario'
    usuario_col = next((col for col in df.columns if col.strip().lower() == 'beneficiario'), None)
    
    # Detectar columna 'pagador'
    pagador_col = next((col for col in df.columns if col.strip().lower() == 'pagador'), None)

    # Detectar columna 'id pagador' (user ID)
    id_pagador_col = next((col for col in df.columns if col.strip().lower() == 'id pagador'), None)

    if not usuario_col or not pagador_col or not id_pagador_col or 'CANTIDAD' not in df.columns or 'FECHA' not in df.columns or 'ESTADO DEL PAGO' not in df.columns:
        st.warning("⚠️ Faltan columnas necesarias: 'beneficiario', 'pagador', 'ID PAGADOR', 'CANTIDAD', 'FECHA' o 'ESTADO DEL PAGO'.")
        return None

    # Filtrar pagos confirmados
    df = df[df['ESTADO DEL PAGO'].astype(str).str.strip().str.lower() == 'true']

    # Excluir Bonus
    if 'FORMAS DE PAGO' in df.columns:
        df = df[~df['FORMAS DE PAGO'].astype(str).str.lower().isin(['bonus csv', 'bonus card'])]

    df["CANTIDAD"] = pd.to_numeric(df["CANTIDAD"], errors="coerce").abs()
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df["hora"] = df["FECHA"].dt.hour

    # Validar que pagador == beneficiario y asignar user_id o "revisar ID"
    df["pagador_equals_beneficiario"] = df[pagador_col].astype(str).str.strip() == df[usuario_col].astype(str).str.strip()
    
    # Crear columna de user_id con validación
    df["user_id_temp"] = df.apply(
        lambda row: pd.to_numeric(row[id_pagador_col], errors="coerce") if row["pagador_equals_beneficiario"] else "revisar ID",
        axis=1
    )

    # Tomar el primer user_id por usuario (si todos coinciden, tomará el correcto; si hay "revisar ID", lo marcará)
    df_ids = df[[usuario_col, "user_id_temp"]].drop_duplicates().dropna()
    df_ids = df_ids.rename(columns={usuario_col: "usuario", "user_id_temp": "user_id"})
    
    # Si hay múltiples valores de user_id para un mismo usuario, marcar como "revisar ID"
    user_id_counts = df_ids.groupby("usuario")["user_id"].nunique()
    usuarios_conflictivos = user_id_counts[user_id_counts > 1].index.tolist()
    
    for usuario in usuarios_conflictivos:
        df_ids.loc[df_ids["usuario"] == usuario, "user_id"] = "revisar ID"
    
    # Eliminar duplicados, manteniendo la última fila por usuario
    df_ids = df_ids.drop_duplicates(subset=["usuario"], keep="last")

    resumen = df.groupby(usuario_col).agg(
        deposito_total=("CANTIDAD", "sum"),
        deposito_maximo=("CANTIDAD", "max"),
        deposito_minimo=("CANTIDAD", "min")
    ).reset_index().rename(columns={usuario_col: "usuario"})

    # Agregar ID PAGADOR con validación
    resumen = resumen.merge(df_ids, on="usuario", how="left")

    # Agregar depósito máximo entre 17 y 23 hs
    filtro_horario = df[df["hora"].between(17, 23)]
    max_17_23 = filtro_horario.groupby(usuario_col)["CANTIDAD"].max().reset_index()
    max_17_23.columns = ["usuario", "deposito_max_17_23"]
    resumen = resumen.merge(max_17_23, on="usuario", how="left")

    return resumen


# === PROCESAMIENTO ===
if archivo_jugado and archivo_depositos:
    df_jugado = procesar_jugado(archivo_jugado)
    df_depositos = procesar_depositos(archivo_depositos)

    if df_jugado is not None and df_depositos is not None:
        df = pd.merge(df_jugado, df_depositos, on="usuario", how="inner")
        
        # Elegir base de cálculo de depósito
        if tipo_deposito == "Suma de depósitos":
            base = df["deposito_total"]
        elif tipo_deposito == "Depósito máximo":
            base = df["deposito_maximo"]
        else:
            base = df["deposito_minimo"]

        # Condición de bonificable y cálculo del bono
        df["bonificable"] = (base >= deposito_minimo) & (df["total_jugado"] >= jugado_minimo)
        df["bono"] = np.where(df["bonificable"], np.minimum(base * porcentaje_bono / 100, tope_bono), 0)
        df["bono"] = df["bono"].round()

        # Cálculo de rollover sobre base de depósito
        if aplica_rollover and cant_rollover:
            df["rollover"] = base * cant_rollover
        else:
            df["rollover"] = 0

        st.subheader("🎯 Usuarios bonificables")
        st.dataframe(df)

        # Descargar resultados
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Bonificables")
        output.seek(0)

        st.download_button("📥 Descargar Excel", data=output, file_name="usuarios_bonificables.xlsx", mime="application/octet-stream")
