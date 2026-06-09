import streamlit as st
import numpy as np
import requests
import os
import onnxruntime as ort
from PIL import Image
from datetime import datetime
from streamlit_paste_button import paste_image_button
from atlas import get_atlas

MODEL_FILENAME = "bone_age_model.onnx"
MODEL_URL = "https://huggingface.co/Jeffersonbraga/verorad-bone-age/resolve/main/bone_age_model.onnx"

def vgg16_preprocess(img_array):
    img = img_array.astype(np.float32)[:, :, ::-1]
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

def autocrop(img):
    gray = np.array(img.convert('L')).astype(np.float32)
    cantos = [gray[0,0], gray[0,-1], gray[-1,0], gray[-1,-1]]
    fundo_escuro = sum(c < 100 for c in cantos) >= 3
    mask = gray > 20 if fundo_escuro else gray < 235
    rows, cols = np.any(mask, axis=1), np.any(mask, axis=0)
    if not rows.any() or not cols.any():
        return img
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    h, w = gray.shape
    pad_r = max(8, int((rmax - rmin) * 0.03))
    pad_c = max(8, int((cmax - cmin) * 0.03))
    rmin, rmax = max(0, rmin - pad_r), min(h, rmax + pad_r)
    cmin, cmax = max(0, cmin - pad_c), min(w, cmax + pad_c)
    cropped = img.crop((cmin, rmin, cmax, rmax))
    area_orig = img.size[0] * img.size[1]
    area_crop = cropped.size[0] * cropped.size[1]
    return cropped if area_crop < area_orig * 0.90 else img

def analisar_imagem(img):
    session = carregar_modelo()
    img = autocrop(img)
    img_resized = img.resize((384, 384), Image.LANCZOS)
    img_array = np.array(img_resized).astype(np.float32)
    img_batch = np.expand_dims(vgg16_preprocess(img_array), axis=0)
    input_name = session.get_inputs()[0].name
    resultado = session.run(None, {input_name: img_batch})
    idade_meses = max(0, float(resultado[0][0][0]))
    anos = int(idade_meses // 12)
    meses = int(round(idade_meses % 12))
    if meses == 12:
        anos += 1
        meses = 0
    return anos, meses, idade_meses

def calcular_concordancia(anos, meses, idade_cron):
    if not idade_cron or "," not in idade_cron:
        return "", ""
    try:
        partes = idade_cron.replace(";", ",").split(",")
        ic_anos, ic_meses = int(partes[0].strip()), int(partes[1].strip())
        diff = (anos * 12 + meses) - (ic_anos * 12 + ic_meses)
        if abs(diff) <= 12:
            return "Compatível com IC", "badge-ok"
        elif diff > 12:
            return f"Avançada +{abs(diff)}m", "badge-av"
        else:
            return f"Atrasada -{abs(diff)}m", "badge-at"
    except:
        return "", ""

def gerar_laudo(anos, meses, sexo, idade_cron):
    sexo_txt = "masculino" if sexo == "Masculino" else "feminino"
    concordancia_txt = ""
    if idade_cron and "," in idade_cron:
        try:
            partes = idade_cron.replace(";", ",").split(",")
            ic_anos, ic_meses = int(partes[0].strip()), int(partes[1].strip())
            diff = (anos * 12 + meses) - (ic_anos * 12 + ic_meses)
            if abs(diff) <= 12:
                concordancia_txt = " Idade óssea compatível com a idade cronológica."
            elif diff > 12:
                concordancia_txt = f" Idade óssea avançada em relação à cronológica (+{abs(diff)} meses)."
            else:
                concordancia_txt = f" Idade óssea atrasada em relação à cronológica (-{abs(diff)} meses)."
        except:
            pass
    return (
        f"Radiografia de mão e punho esquerdos do sexo {sexo_txt}. "
        f"A avaliação automatizada da maturação esquelética por IA estima a idade óssea "
        f"em aproximadamente {anos} anos e {meses} meses.{concordancia_txt} "
        f"Resultado gerado por sistema de auxílio diagnóstico — correlacionar com dados clínicos."
    )

# ── PAGE CONFIG ──
st.set_page_config(page_title="VeroRad | Bone Age AI", page_icon="🩻", layout="wide")

if "historico" not in st.session_state:
    st.session_state.historico = []
if "img_raw" not in st.session_state:
    st.session_state.img_raw = None
if "resultado" not in st.session_state:
    st.session_state.resultado = None

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400&display=swap');

*, html, body { font-family: 'Inter', sans-serif !important; }
.stApp { background: #F3F4F6 !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* TOPBAR */
.vr-top {
    background: #fff;
    border-bottom: 1px solid #E5E7EB;
    padding: 0 2rem;
    height: 52px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.vr-logo { font-size: 1.1rem; font-weight: 700; color: #111827; letter-spacing: -0.025em; }
.vr-logo em { color: #2563EB; font-style: normal; }
.vr-tag { font-size: 0.65rem; color: #9CA3AF; letter-spacing: 0.1em; text-transform: uppercase; margin-left: 10px; }
.vr-online {
    display: flex; align-items: center; gap: 7px;
    font-size: 0.72rem; font-weight: 500; color: #059669;
    background: #D1FAE5; padding: 4px 12px; border-radius: 99px;
}
.vr-online::before {
    content: ''; display: block; width: 6px; height: 6px;
    border-radius: 50%; background: #059669;
}

/* PANELS */
.vr-panel {
    background: #fff;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    margin-bottom: 1rem;
}
.vr-lbl {
    font-size: 0.62rem; font-weight: 600; color: #9CA3AF;
    letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 0.6rem;
}

/* RESULTADO */
.vr-result-row {
    display: flex; align-items: center;
    justify-content: space-between;
    padding-bottom: 0.85rem;
    border-bottom: 1px solid #F3F4F6;
    margin-bottom: 0.85rem;
}
.vr-age {
    font-size: 3.2rem; font-weight: 700;
    color: #111827; line-height: 1; letter-spacing: -0.05em;
}
.vr-age span { font-size: 1.3rem; font-weight: 400; color: #9CA3AF; }
.vr-meta { font-size: 0.7rem; color: #9CA3AF; font-family: 'JetBrains Mono', monospace; margin-top: 3px; }

/* BADGES */
.vr-badge { padding: 5px 12px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; }
.badge-ok { background: #F0FDF4; color: #15803D; border: 1px solid #BBF7D0; }
.badge-av { background: #FEF2F2; color: #B45309; border: 1px solid #FECACA; }
.badge-at { background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; }

/* LAUDO */
.vr-laudo {
    background: #F8FAFC;
    border-left: 3px solid #2563EB;
    border-radius: 0 8px 8px 0;
    padding: 0.85rem 2.5rem 0.85rem 1rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem; color: #334155; line-height: 1.65;
    position: relative; margin-bottom: 0.75rem;
}
.vr-copy-btn {
    position: absolute; top: 8px; right: 8px;
    background: #fff; border: 1px solid #E2E8F0;
    color: #64748B; font-size: 0.65rem; font-weight: 600;
    padding: 3px 8px; border-radius: 4px; cursor: pointer;
    font-family: 'Inter', sans-serif;
}
.vr-copy-btn:hover { background: #F1F5F9; }

/* ATLAS */
.vr-atlas-panel {
    background: #F8FAFC;
    border: 1px solid #E5E7EB;
    border-radius: 10px;
    padding: 1rem 1.25rem;
}
.vr-atlas-title { font-size: 0.7rem; font-weight: 600; color: #2563EB; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 0.75rem; }
.vr-atlas-section { font-size: 0.62rem; font-weight: 600; color: #6B7280; letter-spacing: 0.1em; text-transform: uppercase; margin: 0 0 0.4rem 0; }
.vr-atlas-item { font-size: 0.78rem; color: #4B5563; line-height: 1.55; padding: 0.18rem 0 0.18rem 0.8rem; border-left: 2px solid #E5E7EB; margin-bottom: 0.2rem; }
.vr-atlas-ref { font-size: 0.62rem; color: #D1D5DB; font-family: 'JetBrains Mono', monospace; margin-top: 0.6rem; }

/* NOTICE */
.vr-notice { background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 6px; padding: 0.55rem 0.85rem; font-size: 0.7rem; color: #92400E; }

/* INSTRUÇÃO */
.vr-hint {
    background: #EFF6FF; border: 1px solid #DBEAFE;
    border-radius: 8px; padding: 0.7rem 0.9rem;
    font-size: 0.74rem; color: #1E40AF; line-height: 1.7;
    margin-bottom: 0.75rem;
}
.vr-hint kbd {
    background: #E0E7FF; padding: 1px 5px;
    border-radius: 4px; font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
}

/* HISTÓRICO */
.vr-hist {
    background: #fff; border: 1px solid #F3F4F6;
    border-radius: 8px; padding: 0.6rem 0.85rem;
    margin-bottom: 0.4rem;
    display: flex; justify-content: space-between; align-items: center;
}
.vr-hist-age { font-size: 0.9rem; font-weight: 600; color: #111827; }
.vr-hist-sub { font-size: 0.65rem; color: #9CA3AF; font-family: 'JetBrains Mono', monospace; }
.badge-m { background: #EFF6FF; color: #2563EB; font-size: 0.6rem; font-weight: 600; padding: 2px 7px; border-radius: 4px; }
.badge-f { background: #FDF4FF; color: #9333EA; font-size: 0.6rem; font-weight: 600; padding: 2px 7px; border-radius: 4px; }

/* PLACEHOLDER */
.vr-placeholder {
    background: #F8FAFC; border: 1.5px dashed #CBD5E1;
    border-radius: 12px; height: 240px;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    color: #CBD5E1; gap: 10px;
}

/* STREAMLIT OVERRIDES */
div[data-testid="stSelectbox"] label,
div[data-testid="stTextInput"] label,
div[data-testid="stFileUploader"] label { display: none !important; }
.stButton > button {
    border-radius: 8px !important; font-weight: 600 !important;
    font-size: 0.82rem !important; width: 100% !important;
    height: 38px !important; transition: all 0.15s !important;
}
.stButton > button[kind="primary"] {
    background: #2563EB !important; color: #fff !important; border: none !important;
}
.stButton > button[kind="primary"]:hover {
    background: #1D4ED8 !important; transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
    background: #F9FAFB !important; color: #6B7280 !important;
    border: 1px solid #E5E7EB !important;
}
div[data-testid="stFileUploader"] { padding: 0.25rem !important; }
</style>
""", unsafe_allow_html=True)

# TOPBAR
st.markdown("""
<div class="vr-top">
    <div>
        <span class="vr-logo">Vero<em>Rad</em></span>
        <span class="vr-tag">Bone Age AI</span>
    </div>
    <div class="vr-online">Sistema operacional</div>
</div>
""", unsafe_allow_html=True)

# COLUNAS
col_l, col_m, col_r = st.columns([1, 1.1, 1.7], gap="medium")

# ══════════════ COLUNA ESQUERDA ══════════════
with col_l:
    st.markdown('<div style="padding:1rem 0.5rem 0">', unsafe_allow_html=True)

    st.markdown('<div class="vr-lbl">Dados do paciente</div>', unsafe_allow_html=True)
    sexo = st.selectbox("sexo", ["Masculino", "Feminino"], label_visibility="collapsed")
    idade_cron = st.text_input("ic", placeholder="Idade cronológica (ex: 8, 6)", label_visibility="collapsed")

    st.markdown('<div class="vr-hint"><b>Como capturar:</b><br>1. No PACS, maximize a radiografia<br>2. Pressione <kbd>Win + Shift + S</kbd><br>3. Selecione <b>só a mão e o punho</b><br>4. Clique em 📋 Colar abaixo</div>', unsafe_allow_html=True)

    st.markdown('<div class="vr-lbl">Radiografia</div>', unsafe_allow_html=True)
    paste_result = paste_image_button(label="📋  Colar imagem")
    upload = st.file_uploader("up", type=["png","jpg","jpeg"], label_visibility="collapsed")

    nova_img = None
    if paste_result and paste_result.image_data:
        nova_img = paste_result.image_data.convert("RGB")
    elif upload:
        nova_img = Image.open(upload).convert("RGB")

    if nova_img is not None:
        st.session_state.img_raw = nova_img
        st.session_state.resultado = None

    # Histórico
    if st.session_state.historico:
        st.markdown('<div class="vr-lbl" style="margin-top:1.5rem">Histórico da sessão</div>', unsafe_allow_html=True)
        for item in st.session_state.historico[:8]:
            bc = "badge-m" if item["sexo"] == "Masculino" else "badge-f"
            bl = "M" if item["sexo"] == "Masculino" else "F"
            st.markdown(f"""
            <div class="vr-hist">
                <div>
                    <div class="vr-hist-age">{item['anos']}a {item['meses']:02d}m</div>
                    <div class="vr-hist-sub">{item['meses_totais']:.1f}m · {item['horario']}</div>
                </div>
                <span class="{bc}">{bl}</span>
            </div>
            """, unsafe_allow_html=True)
        if st.button("Limpar histórico", type="secondary"):
            st.session_state.historico = []
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# ══════════════ COLUNA CENTRAL — IMAGEM ══════════════
with col_m:
    st.markdown('<div style="padding:1rem 0.5rem 0">', unsafe_allow_html=True)
    st.markdown('<div class="vr-lbl">Radiografia carregada</div>', unsafe_allow_html=True)

    if st.session_state.img_raw:
        st.image(st.session_state.img_raw, use_container_width=True)
    else:
        st.markdown("""
        <div class="vr-placeholder">
            <div style="font-size:2.2rem">🩻</div>
            <div style="font-size:0.78rem">Nenhuma imagem carregada</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ══════════════ COLUNA DIREITA — RESULTADO ══════════════
with col_r:
    st.markdown('<div style="padding:1rem 0.5rem 0">', unsafe_allow_html=True)

    # Análise automática
    if st.session_state.img_raw and st.session_state.resultado is None:
        try:
            with st.spinner("Analisando..."):
                st.session_state.resultado = analisar_imagem(st.session_state.img_raw)
                # Salva no histórico
                anos, meses, idade_meses = st.session_state.resultado
                if not st.session_state.historico or st.session_state.historico[0].get("meses_totais") != idade_meses:
                    st.session_state.historico.insert(0, {
                        "anos": anos, "meses": meses, "sexo": sexo,
                        "horario": datetime.now().strftime("%H:%M"),
                        "meses_totais": idade_meses
                    })
                    if len(st.session_state.historico) > 20:
                        st.session_state.historico = st.session_state.historico[:20]
        except Exception as e:
            st.error(f"Erro: {e}")

    if st.session_state.resultado:
        anos, meses, idade_meses = st.session_state.resultado
        conc_txt, conc_class = calcular_concordancia(anos, meses, idade_cron)
        badge_html = f'<span class="vr-badge {conc_class}">{conc_txt}</span>' if conc_txt else ""
        laudo = gerar_laudo(anos, meses, sexo, idade_cron)

        # Resultado principal
        st.markdown(f"""
        <div class="vr-panel">
            <div class="vr-result-row">
                <div>
                    <div class="vr-age">{anos}<span>a </span>{meses:02d}<span>m</span></div>
                    <div class="vr-meta">{idade_meses:.2f} meses · {sexo} · Autocrop ativo</div>
                </div>
                {badge_html}
            </div>
            <div class="vr-lbl">Texto para laudo</div>
            <div class="vr-laudo" id="laudo-txt">
                {laudo}
                <button class="vr-copy-btn"
                    onclick="navigator.clipboard.writeText(document.getElementById('laudo-txt').innerText.replace('Copiar','').trim())">
                    📋 Copiar
                </button>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Atlas em duas colunas
        atlas = get_atlas(idade_meses)
        carpo_html = "".join(f'<div class="vr-atlas-item">{i}</div>' for i in atlas["carpo"])
        epif_html  = "".join(f'<div class="vr-atlas-item">{i}</div>' for i in atlas["epifises"])

        st.markdown(f"""
        <div class="vr-atlas-panel">
            <div class="vr-atlas-title">📖 Atlas G&P — {atlas['titulo']}</div>
            <div style="display:flex;gap:1.5rem">
                <div style="flex:1">
                    <div class="vr-atlas-section">Carpo</div>
                    {carpo_html}
                </div>
                <div style="flex:1">
                    <div class="vr-atlas-section">Epífises</div>
                    {epif_html}
                </div>
            </div>
            <div class="vr-atlas-ref">{atlas['referencia_gp']}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="vr-notice" style="margin-top:0.75rem">⚠️ Ferramenta de auxílio diagnóstico. Não substitui avaliação do radiologista responsável.</div>', unsafe_allow_html=True)

    else:
        st.markdown("""
        <div class="vr-panel" style="opacity:0.4">
            <div class="vr-result-row">
                <div class="vr-age">--<span>a </span>--<span>m</span></div>
            </div>
            <div style="height:80px;background:#F3F4F6;border-radius:8px;display:flex;
                align-items:center;justify-content:center;color:#9CA3AF;font-size:0.82rem">
                Aguardando radiografia
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)
