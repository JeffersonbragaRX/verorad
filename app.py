import streamlit as st
import numpy as np
import requests
import os
import onnxruntime as ort
from PIL import Image
from datetime import datetime
from streamlit_paste_button import paste_image_button

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
                            progress.progress(pct, text=f"Carregando... {pct}%")
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

def gerar_laudo(anos, meses, sexo, idade_cron):
    sexo_txt = "do sexo masculino" if sexo == "Masculino" else "do sexo feminino"
    concordancia_txt = ""
    if idade_cron:
        try:
            partes = idade_cron.replace(";", ",").split(",")
            ic_anos, ic_meses = int(partes[0].strip()), int(partes[1].strip())
            ic_total = ic_anos * 12 + ic_meses
            io_total = anos * 12 + meses
            diff = io_total - ic_total
            if abs(diff) <= 12:
                concordancia_txt = " Idade óssea compatível com a idade cronológica."
            elif diff > 12:
                concordancia_txt = f" Idade óssea avançada em relação à idade cronológica (diferença de aproximadamente {abs(diff)} meses)."
            else:
                concordancia_txt = f" Idade óssea atrasada em relação à idade cronológica (diferença de aproximadamente {abs(diff)} meses)."
        except:
            pass
    return (
        f"Radiografia de mão e punho esquerdos {sexo_txt}.\n\n"
        f"A avaliação automatizada da maturação esquelética por inteligência artificial "
        f"estima idade óssea de aproximadamente {anos} anos e {meses} meses.{concordancia_txt}\n\n"
        f"Nota: Resultado gerado por sistema de IA. Deve ser correlacionado com dados "
        f"clínicos e avaliação do radiologista responsável."
    )

st.set_page_config(
    page_title="VeroRad — Idade Óssea",
    page_icon="🦴",
    layout="wide"
)

if "historico" not in st.session_state:
    st.session_state.historico = []

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');

*, html, body { font-family: 'DM Sans', sans-serif !important; }

.stApp {
    background: #F7F8FA !important;
}

/* Remove streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 0 !important; max-width: 100% !important; }

/* ── TOP BAR ── */
.vr-topbar {
    background: #FFFFFF;
    border-bottom: 1px solid #E5E8EF;
    padding: 0 2.5rem;
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
}
.vr-brand {
    display: flex;
    align-items: baseline;
    gap: 6px;
}
.vr-brand-name {
    font-size: 1.15rem;
    font-weight: 600;
    color: #0A0E1A;
    letter-spacing: -0.3px;
}
.vr-brand-name em {
    color: #2563EB;
    font-style: normal;
}
.vr-brand-tag {
    font-size: 0.65rem;
    font-weight: 500;
    color: #94A3B8;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    border-left: 1px solid #E2E8F0;
    padding-left: 8px;
    margin-left: 2px;
}
.vr-status {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.72rem;
    color: #64748B;
}
.vr-dot {
    width: 7px; height: 7px;
    background: #22C55E;
    border-radius: 50%;
}

/* ── MAIN GRID ── */
.vr-main {
    display: grid;
    grid-template-columns: 380px 1fr 280px;
    gap: 0;
    min-height: calc(100vh - 56px);
}

/* ── LEFT PANEL ── */
.vr-left {
    background: #FFFFFF;
    border-right: 1px solid #E5E8EF;
    padding: 1.75rem 1.5rem;
}
.vr-section-label {
    font-size: 0.62rem;
    font-weight: 600;
    color: #94A3B8;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 0.85rem;
    margin-top: 1.5rem;
}
.vr-section-label:first-child { margin-top: 0; }

/* ── CENTER ── */
.vr-center {
    padding: 2rem 2.5rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
}

/* ── RESULT BLOCK ── */
.vr-result-wrap {
    width: 100%;
    max-width: 560px;
}
.vr-result-card {
    background: #FFFFFF;
    border: 1px solid #E5E8EF;
    border-radius: 16px;
    padding: 2.5rem 2rem;
    text-align: center;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    margin-bottom: 1.25rem;
}
.vr-result-eyebrow {
    font-size: 0.65rem;
    font-weight: 600;
    color: #94A3B8;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-bottom: 1rem;
}
.vr-result-number {
    font-size: 5rem;
    font-weight: 300;
    color: #0A0E1A;
    line-height: 1;
    letter-spacing: -4px;
}
.vr-result-number strong {
    font-weight: 600;
    color: #2563EB;
}
.vr-result-unit {
    font-size: 1.1rem;
    font-weight: 400;
    color: #64748B;
    letter-spacing: 0;
}
.vr-result-sub {
    font-size: 0.78rem;
    color: #94A3B8;
    margin-top: 0.75rem;
    font-family: 'DM Mono', monospace;
}
.vr-concordancia {
    display: inline-block;
    margin-top: 1rem;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 500;
}
.vr-concordancia.ok { background: #F0FDF4; color: #16A34A; border: 1px solid #BBF7D0; }
.vr-concordancia.avancada { background: #FFF7ED; color: #EA580C; border: 1px solid #FED7AA; }
.vr-concordancia.atrasada { background: #EFF6FF; color: #2563EB; border: 1px solid #BFDBFE; }

/* Laudo */
.vr-laudo-box {
    background: #FFFFFF;
    border: 1px solid #E5E8EF;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    width: 100%;
    max-width: 560px;
    margin-bottom: 1rem;
}
.vr-laudo-label {
    font-size: 0.62rem;
    font-weight: 600;
    color: #94A3B8;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 0.75rem;
}
.vr-laudo-text {
    font-family: 'DM Mono', monospace;
    font-size: 0.78rem;
    color: #374151;
    line-height: 1.75;
    white-space: pre-wrap;
}

/* Aviso regulatório */
.vr-notice {
    width: 100%;
    max-width: 560px;
    background: #FFFBEB;
    border: 1px solid #FDE68A;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    font-size: 0.72rem;
    color: #92400E;
    line-height: 1.5;
}

/* Placeholder */
.vr-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 320px;
    width: 100%;
    max-width: 560px;
    border: 1.5px dashed #CBD5E1;
    border-radius: 16px;
    color: #CBD5E1;
    gap: 12px;
}
.vr-placeholder-icon { font-size: 2.5rem; }
.vr-placeholder-text { font-size: 0.8rem; }

/* ── RIGHT PANEL — HISTÓRICO ── */
.vr-right {
    background: #FFFFFF;
    border-left: 1px solid #E5E8EF;
    padding: 1.75rem 1.25rem;
}
.vr-hist-item {
    border: 1px solid #F1F5F9;
    border-radius: 10px;
    padding: 0.85rem 1rem;
    margin-bottom: 0.5rem;
    background: #FAFBFC;
    cursor: default;
}
.vr-hist-age {
    font-size: 1.05rem;
    font-weight: 600;
    color: #0A0E1A;
    letter-spacing: -0.3px;
}
.vr-hist-meta {
    font-size: 0.68rem;
    color: #94A3B8;
    font-family: 'DM Mono', monospace;
    margin-top: 2px;
}
.vr-hist-badge {
    display: inline-block;
    font-size: 0.6rem;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 4px;
    letter-spacing: 0.05em;
    float: right;
}
.badge-m { background: #EFF6FF; color: #2563EB; }
.badge-f { background: #FDF4FF; color: #9333EA; }

/* Streamlit overrides */
div[data-testid="stSelectbox"] > div,
div[data-testid="stTextInput"] > div > div {
    border-radius: 8px !important;
    border-color: #E5E8EF !important;
    background: #FAFBFC !important;
    font-size: 0.85rem !important;
}
.stButton > button {
    border-radius: 8px !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    width: 100% !important;
    height: 40px !important;
    background: #2563EB !important;
    color: white !important;
    border: none !important;
    letter-spacing: 0.01em !important;
}
.stButton > button:hover { background: #1D4ED8 !important; }
.stButton > button:disabled { background: #E2E8F0 !important; color: #94A3B8 !important; }

div[data-testid="stFileUploader"] {
    border: 1.5px dashed #CBD5E1 !important;
    border-radius: 10px !important;
    background: #FAFBFC !important;
    padding: 0.5rem !important;
}

hr { border-color: #E5E8EF !important; margin: 1.25rem 0 !important; }
</style>
""", unsafe_allow_html=True)

# ── TOP BAR ──
st.markdown("""
<div class="vr-topbar">
    <div class="vr-brand">
        <div class="vr-brand-name">Vero<em>Rad</em></div>
        <div class="vr-brand-tag">Bone Age AI</div>
    </div>
    <div class="vr-status">
        <div class="vr-dot"></div>
        Sistema operacional
    </div>
</div>
""", unsafe_allow_html=True)

# ── 3 COLUNAS ──
col_left, col_center, col_right = st.columns([1.1, 1.8, 0.85])

# ════════════════ PAINEL ESQUERDO ════════════════
with col_left:
    st.markdown('<div class="vr-section-label">Dados do Exame</div>', unsafe_allow_html=True)

    sexo = st.selectbox("Sexo biológico", ["Masculino", "Feminino"], label_visibility="collapsed")

    idade_cron = st.text_input(
        "Idade cronológica",
        placeholder="anos, meses  (ex: 8, 6)",
        label_visibility="collapsed"
    )

    st.markdown('<div class="vr-section-label">Imagem</div>', unsafe_allow_html=True)

    paste_result = paste_image_button(label="📋  Colar da área de transferência")

    upload = st.file_uploader(
        "upload",
        type=["png", "jpg", "jpeg"],
        label_visibility="collapsed"
    )

    img = None
    if paste_result and paste_result.image_data:
        img = paste_result.image_data.convert("RGB")
        st.image(img, use_container_width=True, caption="Imagem colada")
    elif upload:
        img = Image.open(upload).convert("RGB")
        st.image(img, use_container_width=True, caption="Imagem carregada")

    st.markdown("---")
    analisar = st.button("Analisar", disabled=(img is None))

# ════════════════ PAINEL CENTRAL ════════════════
with col_center:
    if analisar and img is not None:
        try:
            with st.spinner("Processando..."):
                anos, meses, idade_meses = analisar_imagem(img)

            # Concordância
            conc_class = ""
            conc_txt = ""
            if idade_cron:
                try:
                    partes = idade_cron.replace(";", ",").split(",")
                    ic_anos, ic_meses = int(partes[0].strip()), int(partes[1].strip())
                    diff = (anos * 12 + meses) - (ic_anos * 12 + ic_meses)
                    if abs(diff) <= 12:
                        conc_class = "ok"
                        conc_txt = "Compatível com idade cronológica"
                    elif diff > 12:
                        conc_class = "avancada"
                        conc_txt = f"Avançada · +{abs(diff)} meses"
                    else:
                        conc_class = "atrasada"
                        conc_txt = f"Atrasada · -{abs(diff)} meses"
                except:
                    pass

            conc_html = f'<div class="vr-concordancia {conc_class}">{conc_txt}</div>' if conc_txt else ""

            st.markdown(f"""
            <div class="vr-result-card">
                <div class="vr-result-eyebrow">Idade Óssea Estimada</div>
                <div class="vr-result-number">
                    <strong>{anos}</strong>
                    <span class="vr-result-unit">a</span>
                    <strong>{meses:02d}</strong>
                    <span class="vr-result-unit">m</span>
                </div>
                <div class="vr-result-sub">{idade_meses:.1f} meses · {sexo}</div>
                {conc_html}
            </div>
            """, unsafe_allow_html=True)

            # Laudo
            laudo = gerar_laudo(anos, meses, sexo, idade_cron)
            st.markdown(f"""
            <div class="vr-laudo-box">
                <div class="vr-laudo-label">Texto para Laudo</div>
                <div class="vr-laudo-text">{laudo}</div>
            </div>
            """, unsafe_allow_html=True)
            st.code(laudo, language=None)

            st.markdown("""
            <div class="vr-notice">
                ⚠️ Ferramenta de auxílio diagnóstico. Não substitui avaliação do radiologista responsável.
            </div>
            """, unsafe_allow_html=True)

            # Histórico
            st.session_state.historico.insert(0, {
                "anos": anos, "meses": meses, "sexo": sexo,
                "horario": datetime.now().strftime("%H:%M"),
                "meses_totais": idade_meses
            })
            if len(st.session_state.historico) > 20:
                st.session_state.historico = st.session_state.historico[:20]

        except Exception as e:
            st.error(f"Erro: {e}")
    else:
        st.markdown("""
        <div class="vr-placeholder">
            <div class="vr-placeholder-icon">🩻</div>
            <div class="vr-placeholder-text">Carregue uma radiografia para iniciar</div>
        </div>
        """, unsafe_allow_html=True)

# ════════════════ PAINEL DIREITO — HISTÓRICO ════════════════
with col_right:
    st.markdown('<div class="vr-section-label">Histórico da Sessão</div>', unsafe_allow_html=True)

    if not st.session_state.historico:
        st.markdown('<p style="font-size:0.78rem;color:#CBD5E1">Nenhum exame analisado ainda.</p>', unsafe_allow_html=True)
    else:
        for item in st.session_state.historico:
            badge = "M" if item["sexo"] == "Masculino" else "F"
            bc = "badge-m" if item["sexo"] == "Masculino" else "badge-f"
            st.markdown(f"""
            <div class="vr-hist-item">
                <span class="vr-hist-badge {bc}">{badge}</span>
                <div class="vr-hist-age">{item['anos']}a {item['meses']:02d}m</div>
                <div class="vr-hist-meta">{item['meses_totais']:.1f} meses · {item['horario']}</div>
            </div>
            """, unsafe_allow_html=True)

        if st.button("Limpar", type="secondary"):
            st.session_state.historico = []
            st.rerun()

    st.markdown("---")
    st.markdown('<div class="vr-section-label">Sobre</div>', unsafe_allow_html=True)
    st.markdown('<p style="font-size:0.72rem;color:#94A3B8;line-height:1.6">Modelo VGG16 treinado no dataset RSNA Pediatric Bone Age Challenge. Saída em meses, convertida para anos e meses.</p>', unsafe_allow_html=True)
