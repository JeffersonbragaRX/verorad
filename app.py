import streamlit as st
import numpy as np
import requests
import os
import onnxruntime as ort
from PIL import Image

# --- CONFIGURAÇÃO ---
MODEL_FILENAME = "bone_age_model.onnx"
MODEL_URL = "https://huggingface.co/Jeffersonbraga/verorad-bone-age/resolve/main/bone_age_model.onnx"

def vgg16_preprocess(img_array):
    """Preprocessing idêntico ao treinamento: RGB->BGR + subtração média ImageNet."""
    img = img_array.astype(np.float32)
    img = img[:, :, ::-1]       # RGB -> BGR
    img[:, :, 0] -= 103.939     # B
    img[:, :, 1] -= 116.779     # G
    img[:, :, 2] -= 123.68      # R
    return img

@st.cache_resource
def carregar_modelo():
    if not os.path.exists(MODEL_FILENAME):
        with st.spinner("Baixando modelo (apenas na primeira vez)..."):
            with requests.get(MODEL_URL, stream=True) as r:
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                downloaded = 0
                progress = st.progress(0, text="Baixando modelo...")
                with open(MODEL_FILENAME, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = int(downloaded / total * 100)
                            progress.progress(pct, text=f"Baixando modelo... {pct}%")
                progress.empty()

    if os.path.getsize(MODEL_FILENAME) < 1_000_000:
        os.remove(MODEL_FILENAME)
        raise RuntimeError("Arquivo corrompido. Verifique o link do modelo.")

    return ort.InferenceSession(MODEL_FILENAME)

# --- INTERFACE ---
st.set_page_config(
    page_title="VeroRad — Idade Óssea",
    page_icon="🦴",
    layout="centered"
)

st.title("🦴 VeroRad")
st.caption("Estimativa automatizada de idade óssea por IA")
st.divider()

st.info(
    "**Como usar:** envie uma radiografia de mão e punho (PA). "
    "O modelo estimará a idade óssea com base no padrão de maturação esquelética.",
    icon="ℹ️"
)

upload = st.file_uploader(
    "Selecione a radiografia:",
    type=["png", "jpg", "jpeg"],
    help="Formatos aceitos: PNG, JPG, JPEG"
)

if upload:
    img = Image.open(upload).convert("RGB")
    st.image(img, caption="Imagem carregada", use_container_width=True)
    st.divider()

    if st.button("🔍 Analisar Idade Óssea", type="primary", use_container_width=True):
        try:
            session = carregar_modelo()

            with st.spinner("Analisando..."):
                img_resized = img.resize((384, 384), Image.LANCZOS)
                img_array = np.array(img_resized).astype(np.float32)
                img_preprocessed = vgg16_preprocess(img_array)
                img_batch = np.expand_dims(img_preprocessed, axis=0)

                input_name = session.get_inputs()[0].name
                resultado = session.run(None, {input_name: img_batch})

                idade_meses = float(resultado[0][0][0])
                idade_meses = max(0, idade_meses)

                anos = int(idade_meses // 12)
                meses = int(round(idade_meses % 12))
                if meses == 12:
                    anos += 1
                    meses = 0

            st.success(f"**Idade óssea estimada: {anos} anos e {meses} meses**")
            st.caption(f"Equivalente a {idade_meses:.1f} meses totais")

            st.warning(
                "⚠️ Este resultado é uma estimativa gerada por IA e **não substitui** "
                "a avaliação de um médico radiologista. Use como ferramenta auxiliar.",
                icon="⚠️"
            )

        except Exception as e:
            st.error(f"Erro durante a análise: {e}")

st.divider()
st.caption("VeroRad © 2025 — Ferramenta de suporte diagnóstico em radiologia pediátrica")
