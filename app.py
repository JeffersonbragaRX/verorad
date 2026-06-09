import streamlit as st
import numpy as np
import requests
import os
import onnxruntime as ort
from PIL import Image
from datetime import datetime
from streamlit_paste_button import paste_image_button

# --- CONFIGURAÇÃO ---
MODEL_FILENAME = "bone_age_model.onnx"
MODEL_URL = "https://huggingface.co/Jeffersonbraga/verorad-bone-age/resolve/main/bone_age_model.onnx"

def vgg16_preprocess(img_array):
    img = img_array.astype(np.float32)
    img = img[:, :, ::-1]
    img[:, :, 0] -= 103.939
    img[:, :, 1] -= 116.779
    img[:, :, 2] -= 123.68
    return img

@st.cache_resource
def carregar_modelo():
    if not os.path.exists(MODEL_FILENAME):
        with st.spinner("Carregando modelo..."):
            with requests.get(MODEL_URL, stream=True) as r:
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                downloaded = 0
                progress = st.progress(0, text="Inicializando...")
                with open(MODEL_FILENAME, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = int(downloaded / total * 100)
                            progress.progress(pct, text=f"Carregando modelo... {pct}%")
                progress.empty()
    if os.path.getsize(MODEL_FILENAME) < 1_000_000:
        os.remove(MODEL_FILENAME)
        raise RuntimeError("Arquivo corrompido.")
    return ort.InferenceSession(MODEL_FILENAME)

def analisar_imagem(img):
    session = carregar_modelo()
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
    return anos, meses, idade_meses

def gerar_laudo(anos, meses, sexo, idade_cronologica):
    sexo_txt = "do sexo masculino" if sexo == "Masculino" else "do sexo feminino"
    resultado_txt = f"{anos} anos e {meses} meses"
    
    if idade_cronologica:
        try:
            ic_anos, ic_meses = map(int, idade_cronologica.split(","))
            ic_total = ic_anos * 12 + ic_meses
            io_total = anos * 12 + meses
            diff = io_total - ic_total
            if abs(diff) <= 12:
                concordancia = "compatível com a idade cronológica"
            elif diff > 12:
                concordancia = f"avançada em relação à idade cronológica (diferença de {abs(diff)} meses)"
            else:
                concordancia = f"atrasada em relação à idade cronológica (diferença de {abs(diff)} meses)"
            concordancia_txt = f" Idade óssea {concordancia}."
        except:
            concordancia_txt = ""
    else:
        concordancia_txt = ""

    laudo = (
        f"Radiografia de mão e punho esquerdos {sexo_txt}.\n\n"
        f"A avaliação da maturação esquelética pelo método automatizado (IA) estima "
        f"idade óssea de aproximadamente {resultado_txt}.{concordancia_txt}\n\n"
        f"Nota: Este resultado foi gerado por sistema de inteligência artificial e "
        f"deve ser correlacionado com dados clínicos e avaliação do radiologista responsável."
    )
    return laudo

# --- PÁGINA ---
st.set_page_config(
    page_title="VeroRad — Idade Óssea",
    page_icon="🦴",
    layout="wide"
)

# CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .stApp {
        background-color: #0A0F1E;
    }

    /* Header */
    .vr-header {
        padding: 2rem 0 1.5rem 0;
        border-bottom: 1px solid #1E2D4A;
        margin-bottom: 2rem;
    }
    .vr-logo {
        font-size: 1.6rem;
        font-weight: 700;
        color: #FFFFFF;
        letter-spacing: -0.5px;
    }
    .vr-logo span {
        color: #3B82F6;
    }
    .vr-tagline {
        font-size: 0.78rem;
        color: #4B6087;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-top: 2px;
    }

    /* Cards */
    .vr-card {
        background: #0F1729;
        border: 1px solid #1E2D4A;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    .vr-card-title {
        font-size: 0.7rem;
        font-weight: 600;
        color: #3B82F6;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 1rem;
    }

    /* Resultado */
    .vr-result-main {
        background: linear-gradient(135deg, #0F1729 0%, #0D1F3C 100%);
        border: 1px solid #2563EB;
        border-radius: 12px;
        padding: 2rem;
        text-align: center;
        margin: 1rem 0;
    }
    .vr-result-label {
        font-size: 0.72rem;
        color: #4B6087;
        letter-spacing: 0.15em;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }
    .vr-result-value {
        font-size: 3rem;
        font-weight: 700;
        color: #FFFFFF;
        line-height: 1;
        letter-spacing: -2px;
    }
    .vr-result-sub {
        font-size: 0.85rem;
        color: #4B6087;
        margin-top: 0.5rem;
        font-family: 'JetBrains Mono', monospace;
    }

    /* Histórico */
    .vr-history-item {
        background: #0F1729;
        border: 1px solid #1E2D4A;
        border-radius: 8px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 0.5rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .vr-history-age {
        font-size: 1rem;
        font-weight: 600;
        color: #FFFFFF;
    }
    .vr-history-meta {
        font-size: 0.72rem;
        color: #4B6087;
        font-family: 'JetBrains Mono', monospace;
    }
    .vr-badge {
        font-size: 0.65rem;
        padding: 2px 8px;
        border-radius: 20px;
        font-weight: 600;
        letter-spacing: 0.05em;
    }
    .vr-badge-m { background: #1E3A5F; color: #60A5FA; }
    .vr-badge-f { background: #3B1F5E; color: #C084FC; }

    /* Laudo */
    .vr-laudo {
        background: #070D1A;
        border: 1px solid #1E2D4A;
        border-left: 3px solid #3B82F6;
        border-radius: 8px;
        padding: 1.25rem;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
        color: #94A3B8;
        line-height: 1.7;
        white-space: pre-wrap;
    }

    /* Aviso */
    .vr-warning {
        background: #1A1200;
        border: 1px solid #854D0E;
        border-radius: 8px;
        padding: 0.9rem 1.1rem;
        font-size: 0.78rem;
        color: #A16207;
        margin-top: 1rem;
    }

    /* Botão analisar */
    .stButton > button {
        background: #2563EB !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 0.65rem 1.5rem !important;
        width: 100% !important;
        transition: background 0.2s !important;
    }
    .stButton > button:hover {
        background: #1D4ED8 !important;
    }

    /* Inputs */
    .stTextInput input, .stSelectbox select {
        background: #0F1729 !important;
        border: 1px solid #1E2D4A !important;
        color: #E2E8F0 !important;
        border-radius: 8px !important;
    }

    /* Hide streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Divider */
    hr {border-color: #1E2D4A !important;}
</style>
""", unsafe_allow_html=True)

# Inicializa histórico
if "historico" not in st.session_state:
    st.session_state.historico = []

# --- HEADER ---
st.markdown("""
<div class="vr-header">
    <div class="vr-logo">Vero<span>Rad</span></div>
    <div class="vr-tagline">Estimativa de Idade Óssea por IA · Radiologia Pediátrica</div>
</div>
""", unsafe_allow_html=True)

# --- LAYOUT PRINCIPAL ---
col_esq, col_dir = st.columns([1.1, 1], gap="large")

with col_esq:
    # DADOS DO PACIENTE
    st.markdown('<div class="vr-card-title">📋 Dados do Exame</div>', unsafe_allow_html=True)

    col_s, col_i = st.columns(2)
    with col_s:
        sexo = st.selectbox("Sexo biológico", ["Masculino", "Feminino"], label_visibility="visible")
    with col_i:
        idade_cron = st.text_input("Idade cronológica (opcional)", placeholder="ex: 8,6  →  anos,meses")

    st.markdown("---")

    # ENTRADA DE IMAGEM
    st.markdown('<div class="vr-card-title">🩻 Radiografia de Mão e Punho (PA)</div>', unsafe_allow_html=True)

    paste_result = paste_image_button(
        label="📋 Colar imagem da área de transferência",
        help="Copie a imagem (Ctrl+C) e clique aqui para colar"
    )

    upload = st.file_uploader(
        "ou selecione o arquivo:",
        type=["png", "jpg", "jpeg"],
        label_visibility="visible"
    )

    img = None
    if paste_result and paste_result.image_data:
        img = paste_result.image_data.convert("RGB")
        st.image(img, use_container_width=True)
    elif upload:
        img = Image.open(upload).convert("RGB")
        st.image(img, use_container_width=True)

    st.markdown("---")

    analisar = st.button("Analisar Idade Óssea", disabled=(img is None))

with col_dir:
    if analisar and img is not None:
        try:
            with st.spinner("Processando..."):
                anos, meses, idade_meses = analisar_imagem(img)

            # Resultado principal
            st.markdown(f"""
            <div class="vr-result-main">
                <div class="vr-result-label">Idade Óssea Estimada</div>
                <div class="vr-result-value">{anos}<span style="font-size:1.5rem;color:#4B6087"> a </span>{meses}<span style="font-size:1.5rem;color:#4B6087"> m</span></div>
                <div class="vr-result-sub">{idade_meses:.1f} meses totais · {sexo}</div>
            </div>
            """, unsafe_allow_html=True)

            # Laudo gerado
            st.markdown('<div class="vr-card-title" style="margin-top:1.5rem">📄 Texto para Laudo</div>', unsafe_allow_html=True)
            laudo = gerar_laudo(anos, meses, sexo, idade_cron if idade_cron else None)
            st.markdown(f'<div class="vr-laudo">{laudo}</div>', unsafe_allow_html=True)
            st.code(laudo, language=None)

            # Aviso
            st.markdown("""
            <div class="vr-warning">
                ⚠️ Resultado gerado por IA. Não substitui avaliação do radiologista responsável. 
                Use como ferramenta auxiliar de fluxo de trabalho.
            </div>
            """, unsafe_allow_html=True)

            # Adiciona ao histórico
            st.session_state.historico.insert(0, {
                "anos": anos,
                "meses": meses,
                "sexo": sexo,
                "horario": datetime.now().strftime("%H:%M"),
                "meses_totais": idade_meses
            })
            if len(st.session_state.historico) > 20:
                st.session_state.historico = st.session_state.historico[:20]

        except Exception as e:
            st.error(f"Erro na análise: {e}")

    elif not analisar:
        # Placeholder
        st.markdown("""
        <div style="height:200px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#1E2D4A;border:1px dashed #1E2D4A;border-radius:12px;margin-top:0.5rem">
            <div style="font-size:2.5rem">🦴</div>
            <div style="font-size:0.8rem;margin-top:0.5rem;color:#2D3F5E">Aguardando radiografia</div>
        </div>
        """, unsafe_allow_html=True)

    # HISTÓRICO DA SESSÃO
    if st.session_state.historico:
        st.markdown('<div class="vr-card-title" style="margin-top:2rem">🕐 Histórico da Sessão</div>', unsafe_allow_html=True)
        for item in st.session_state.historico:
            badge_class = "vr-badge-m" if item["sexo"] == "Masculino" else "vr-badge-f"
            badge_letra = "M" if item["sexo"] == "Masculino" else "F"
            st.markdown(f"""
            <div class="vr-history-item">
                <div>
                    <div class="vr-history-age">{item['anos']}a {item['meses']}m</div>
                    <div class="vr-history-meta">{item['meses_totais']:.1f} meses · {item['horario']}</div>
                </div>
                <span class="vr-badge {badge_class}">{badge_letra}</span>
            </div>
            """, unsafe_allow_html=True)

        if st.button("Limpar histórico", type="secondary"):
            st.session_state.historico = []
            st.rerun()
