import streamlit as st
import numpy as np
import requests
import os
import onnxruntime as ort
from PIL import Image, ImageDraw
from datetime import datetime
from streamlit_paste_button import paste_image_button
from atlas import get_atlas

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

def autocrop(img):
    """Remove bordas pretas/brancas — detecta fundo automaticamente."""
    gray = np.array(img.convert('L')).astype(np.float32)
    cantos = [gray[0,0], gray[0,-1], gray[-1,0], gray[-1,-1]]
    fundo_escuro = sum(c < 100 for c in cantos) >= 3
    mask = gray > 20 if fundo_escuro else gray < 235
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    if not rows.any() or not cols.any():
        return img
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    h, w = gray.shape
    pad_r = max(8, int((rmax - rmin) * 0.03))
    pad_c = max(8, int((cmax - cmin) * 0.03))
    rmin, rmax = max(0, rmin-pad_r), min(h, rmax+pad_r)
    cmin, cmax = max(0, cmin-pad_c), min(w, cmax+pad_c)
    cropped = img.crop((cmin, rmin, cmax, rmax))
    area_orig = img.size[0] * img.size[1]
    area_crop = cropped.size[0] * cropped.size[1]
    return cropped if area_crop < area_orig * 0.90 else img

def analisar_imagem(img):
    session = carregar_modelo()
    img = autocrop(img)
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
            partes = idade_cron.replace(";",",").split(",")
            ic_anos, ic_meses = int(partes[0].strip()), int(partes[1].strip())
            diff = (anos*12+meses) - (ic_anos*12+ic_meses)
            if abs(diff) <= 12:
                concordancia_txt = " Idade óssea compatível com a idade cronológica."
            elif diff > 12:
                concordancia_txt = f" Idade óssea avançada em relação à idade cronológica (diferença de aproximadamente {abs(diff)} meses)."
            else:
                concordancia_txt = f" Idade óssea atrasada em relação à idade cronológica (diferença de aproximadamente {abs(diff)} meses)."
        except: pass
    return (
        f"Radiografia de mão e punho esquerdos {sexo_txt}. "
        f"A avaliação automatizada da maturação esquelética por IA estima idade óssea de "
        f"aproximadamente {anos} anos e {meses} meses.{concordancia_txt} "
        f"Resultado gerado por sistema de IA — correlacionar com dados clínicos."
    )

# ── PAGE CONFIG ──
st.set_page_config(page_title="VeroRad", page_icon="🦴", layout="wide")

if "historico" not in st.session_state:
    st.session_state.historico = []
if "img_raw" not in st.session_state:
    st.session_state.img_raw = None
if "img_crop" not in st.session_state:
    st.session_state.img_crop = None
if "modo_crop" not in st.session_state:
    st.session_state.modo_crop = False
if "resultado" not in st.session_state:
    st.session_state.resultado = None

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400&display=swap');
*, html, body { font-family: 'DM Sans', sans-serif !important; }
.stApp { background: #F7F8FA !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 !important; max-width: 100% !important; }

.vr-top {
    background: #fff; border-bottom: 1px solid #E5E8EF;
    padding: 0 2rem; height: 48px;
    display: flex; align-items: center; justify-content: space-between;
}
.vr-logo { font-size: 1rem; font-weight: 600; color: #0A0E1A; letter-spacing: -0.3px; }
.vr-logo em { color: #2563EB; font-style: normal; }
.vr-tag { font-size: 0.6rem; color: #94A3B8; letter-spacing: 0.1em; text-transform: uppercase; }
.vr-online { font-size: 0.65rem; color: #22C55E; display:flex; align-items:center; gap:5px; }
.vr-dot { width:6px; height:6px; background:#22C55E; border-radius:50%; display:inline-block; }

.vr-result {
    background: #fff; border: 1px solid #E5E8EF; border-radius: 12px;
    padding: 1.25rem 1.5rem; display: flex; align-items: center;
    justify-content: space-between; margin-bottom: 0.75rem;
}
.vr-result-num { font-size: 2.8rem; font-weight: 300; color: #0A0E1A; letter-spacing: -2px; line-height: 1; }
.vr-result-num strong { font-weight: 600; color: #2563EB; }
.vr-result-num span { font-size: 1rem; color: #94A3B8; font-weight: 400; letter-spacing: 0; }
.vr-result-meta { font-size: 0.72rem; color: #94A3B8; font-family: 'DM Mono', monospace; margin-top: 3px; }
.vr-badge { font-size: 0.68rem; font-weight: 600; padding: 4px 12px; border-radius: 20px; white-space: nowrap; }
.badge-ok { background: #F0FDF4; color: #16A34A; border: 1px solid #BBF7D0; }
.badge-av { background: #FFF7ED; color: #EA580C; border: 1px solid #FED7AA; }
.badge-at { background: #EFF6FF; color: #2563EB; border: 1px solid #BFDBFE; }

.vr-laudo {
    background: #fff; border: 1px solid #E5E8EF; border-left: 3px solid #2563EB;
    border-radius: 8px; padding: 0.9rem 1.1rem;
    font-family: 'DM Mono', monospace; font-size: 0.75rem; color: #374151;
    line-height: 1.65; margin-bottom: 0.75rem;
}
.vr-atlas {
    background: #fff; border: 1px solid #E5E8EF; border-radius: 8px;
    padding: 0.9rem 1.1rem; margin-bottom: 0.75rem;
}
.vr-atlas-title { font-size: 0.65rem; font-weight: 600; color: #94A3B8; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 0.6rem; }
.vr-atlas-section { font-size: 0.62rem; font-weight: 600; color: #2563EB; letter-spacing: 0.1em; text-transform: uppercase; margin: 0.5rem 0 0.3rem 0; }
.vr-atlas-item { font-size: 0.78rem; color: #4B5563; line-height: 1.55; padding: 0.2rem 0 0.2rem 0.85rem; border-left: 2px solid #E5E8EF; margin-bottom: 0.2rem; }
.vr-atlas-ref { font-size: 0.62rem; color: #CBD5E1; font-family: 'DM Mono', monospace; margin-top: 0.5rem; }

.vr-notice { background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 6px; padding: 0.6rem 0.9rem; font-size: 0.7rem; color: #92400E; }
.vr-crop-hint { background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 6px; padding: 0.6rem 0.9rem; font-size: 0.75rem; color: #1D4ED8; margin-bottom: 0.5rem; }

.vr-hist { background: #FAFBFC; border: 1px solid #F1F5F9; border-radius: 8px; padding: 0.6rem 0.85rem; margin-bottom: 0.4rem; display: flex; justify-content: space-between; align-items: center; }
.vr-hist-age { font-size: 0.9rem; font-weight: 600; color: #0A0E1A; }
.vr-hist-sub { font-size: 0.65rem; color: #94A3B8; font-family: 'DM Mono', monospace; }
.badge-m { background:#EFF6FF; color:#2563EB; font-size:0.6rem; font-weight:600; padding:2px 7px; border-radius:4px; }
.badge-f { background:#FDF4FF; color:#9333EA; font-size:0.6rem; font-weight:600; padding:2px 7px; border-radius:4px; }
.vr-lbl { font-size: 0.6rem; font-weight: 600; color: #94A3B8; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 0.5rem; }

div[data-testid="stSelectbox"] label,
div[data-testid="stTextInput"] label,
div[data-testid="stFileUploader"] label { display: none !important; }
.stButton > button {
    border-radius: 8px !important; font-weight: 500 !important;
    font-size: 0.82rem !important; width: 100% !important; height: 38px !important;
    background: #2563EB !important; color: white !important; border: none !important;
}
.stButton > button:hover { background: #1D4ED8 !important; }
.stButton > button:disabled { background: #E2E8F0 !important; color: #94A3B8 !important; }
div[data-testid="stFileUploader"] { padding: 0.25rem !important; }
</style>
""", unsafe_allow_html=True)

# TOPBAR
st.markdown("""
<div class="vr-top">
    <div>
        <span class="vr-logo">Vero<em>Rad</em></span>
        <span class="vr-tag" style="margin-left:10px">Bone Age AI</span>
    </div>
    <div class="vr-online"><span class="vr-dot"></span> Sistema operacional</div>
</div>
""", unsafe_allow_html=True)

col_l, col_c, col_r = st.columns([1, 1.6, 0.75], gap="medium")

# ── ESQUERDO ──
with col_l:
    st.markdown('<div style="padding: 1rem 0.5rem 0 0.5rem">', unsafe_allow_html=True)
    st.markdown('<div class="vr-lbl">Sexo biológico</div>', unsafe_allow_html=True)
    sexo = st.selectbox("sexo", ["Masculino", "Feminino"], label_visibility="collapsed")

    st.markdown('<div class="vr-lbl" style="margin-top:0.75rem">Idade cronológica (opcional)</div>', unsafe_allow_html=True)
    idade_cron = st.text_input("ic", placeholder="anos, meses  (ex: 8, 6)", label_visibility="collapsed")

    st.markdown('<div class="vr-lbl" style="margin-top:0.75rem">Radiografia</div>', unsafe_allow_html=True)
    paste_result = paste_image_button(label="📋  Colar imagem")
    upload = st.file_uploader("up", type=["png","jpg","jpeg"], label_visibility="collapsed")

    # Detecta nova imagem
    nova_img = None
    if paste_result and paste_result.image_data:
        nova_img = paste_result.image_data.convert("RGB")
    elif upload:
        nova_img = Image.open(upload).convert("RGB")

    if nova_img is not None:
        st.session_state.img_raw = nova_img
        st.session_state.img_crop = None
        st.session_state.resultado = None
        st.session_state.modo_crop = False

    # Mostra imagem atual (raw ou crop manual)
    img_exibir = st.session_state.img_crop if st.session_state.img_crop else st.session_state.img_raw

    if img_exibir:
        caption = "✂️ Recorte manual aplicado" if st.session_state.img_crop else "Imagem original"
        st.image(img_exibir, use_container_width=True, caption=caption)

        # Botão de recorte manual
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("✂️ Recortar", type="secondary"):
                st.session_state.modo_crop = True
                st.rerun()
        with col_b2:
            if st.session_state.img_crop and st.button("↩️ Resetar"):
                st.session_state.img_crop = None
                st.session_state.resultado = None
                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# ── CENTRAL ──
with col_c:
    st.markdown('<div style="padding: 1rem 0.5rem 0 0.5rem">', unsafe_allow_html=True)

    # MODO CROP MANUAL
    if st.session_state.modo_crop and st.session_state.img_raw:
        img_raw = st.session_state.img_raw
        W, H = img_raw.size

        st.markdown('<div class="vr-crop-hint">✂️ Ajuste os valores abaixo para enquadrar só a mão e o punho. A prévia atualiza em tempo real.</div>', unsafe_allow_html=True)

        col_a, col_b = st.columns(2)
        with col_a:
            x1_pct = st.number_input("Esquerda %", 0, 49, 5, step=1)
            y1_pct = st.number_input("Superior %", 0, 49, 5, step=1)
        with col_b:
            x2_pct = st.number_input("Direita %", 51, 100, 95, step=1)
            y2_pct = st.number_input("Inferior %", 51, 100, 95, step=1)

        x1 = int(W * x1_pct / 100)
        y1 = int(H * y1_pct / 100)
        x2 = int(W * x2_pct / 100)
        y2 = int(H * y2_pct / 100)

        preview = img_raw.copy()
        draw = ImageDraw.Draw(preview)
        lw = max(3, W // 150)
        draw.rectangle([x1, y1, x2, y2], outline="#2563EB", width=lw)
        st.image(preview, use_container_width=True, caption="Prévia — ajuste os valores acima")

        col_ok, col_cancel = st.columns(2)
        with col_ok:
            if st.button("✅ Aplicar e reanalisar"):
                st.session_state.img_crop = img_raw.crop((x1, y1, x2, y2))
                st.session_state.modo_crop = False
                st.session_state.resultado = None
                st.rerun()
        with col_cancel:
            if st.button("❌ Cancelar"):
                st.session_state.modo_crop = False
                st.rerun()

    # ANÁLISE AUTOMÁTICA
    elif st.session_state.img_raw and not st.session_state.modo_crop:
        img_para_analisar = st.session_state.img_crop if st.session_state.img_crop else st.session_state.img_raw

        # Roda análise automaticamente se não tem resultado ainda
        if st.session_state.resultado is None:
            try:
                with st.spinner("Analisando..."):
                    anos, meses, idade_meses = analisar_imagem(img_para_analisar)
                st.session_state.resultado = (anos, meses, idade_meses)
            except Exception as e:
                st.error(f"Erro: {e}")

        if st.session_state.resultado:
            anos, meses, idade_meses = st.session_state.resultado

            # Concordância
            badge_html = ""
            if idade_cron:
                try:
                    partes = idade_cron.replace(";",",").split(",")
                    ic_anos, ic_meses = int(partes[0].strip()), int(partes[1].strip())
                    diff = (anos*12+meses) - (ic_anos*12+ic_meses)
                    if abs(diff) <= 12:
                        badge_html = '<span class="vr-badge badge-ok">Compatível com IC</span>'
                    elif diff > 12:
                        badge_html = f'<span class="vr-badge badge-av">Avançada · +{abs(diff)}m</span>'
                    else:
                        badge_html = f'<span class="vr-badge badge-at">Atrasada · -{abs(diff)}m</span>'
                except: pass

            st.markdown(f"""
            <div class="vr-result">
                <div>
                    <div class="vr-result-num">
                        <strong>{anos}</strong><span>a </span><strong>{meses:02d}</strong><span>m</span>
                    </div>
                    <div class="vr-result-meta">{idade_meses:.1f} meses · {sexo}</div>
                </div>
                {badge_html}
            </div>
            """, unsafe_allow_html=True)

            laudo = gerar_laudo(anos, meses, sexo, idade_cron)
            laudo_id = "laudo-text"
            st.markdown(f'''
            <div class="vr-laudo" style="position:relative">
                <div id="{laudo_id}">{laudo}</div>
                <button onclick="navigator.clipboard.writeText(document.getElementById('{laudo_id}').innerText)"
                    style="position:absolute;top:8px;right:8px;background:#EFF6FF;border:1px solid #BFDBFE;
                    color:#2563EB;font-size:0.65rem;font-weight:600;padding:3px 10px;border-radius:6px;
                    cursor:pointer;font-family:DM Sans,sans-serif">
                    📋 Copiar
                </button>
            </div>
            ''', unsafe_allow_html=True)

            atlas = get_atlas(idade_meses)
            carpo_html = "".join(f'<div class="vr-atlas-item">{i}</div>' for i in atlas["carpo"])
            epif_html  = "".join(f'<div class="vr-atlas-item">{i}</div>' for i in atlas["epifises"])
            st.markdown(f"""
            <div class="vr-atlas">
                <div class="vr-atlas-title">📖 Atlas G&P — {atlas['titulo']}</div>
                <div class="vr-atlas-section">Carpo</div>{carpo_html}
                <div class="vr-atlas-section">Epífises</div>{epif_html}
                <div class="vr-atlas-ref">{atlas['referencia_gp']}</div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<div class="vr-notice">⚠️ Ferramenta de auxílio diagnóstico. Não substitui avaliação do radiologista responsável.</div>', unsafe_allow_html=True)

            # Histórico
            if len(st.session_state.historico) == 0 or st.session_state.historico[0].get("meses_totais") != idade_meses:
                st.session_state.historico.insert(0, {
                    "anos": anos, "meses": meses, "sexo": sexo,
                    "horario": datetime.now().strftime("%H:%M"),
                    "meses_totais": idade_meses
                })
                if len(st.session_state.historico) > 20:
                    st.session_state.historico = st.session_state.historico[:20]

    else:
        st.markdown("""
        <div style="height:200px;display:flex;flex-direction:column;align-items:center;
            justify-content:center;border:1.5px dashed #CBD5E1;border-radius:12px;
            color:#CBD5E1;gap:10px;margin-top:0.5rem">
            <div style="font-size:2rem">🩻</div>
            <div style="font-size:0.78rem">Cole ou carregue uma radiografia</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ── DIREITO — HISTÓRICO ──
with col_r:
    st.markdown('<div style="padding: 1rem 0.5rem 0 0.5rem">', unsafe_allow_html=True)
    st.markdown('<div class="vr-lbl">Histórico da sessão</div>', unsafe_allow_html=True)
    if not st.session_state.historico:
        st.markdown('<p style="font-size:0.75rem;color:#CBD5E1">Nenhum exame ainda.</p>', unsafe_allow_html=True)
    else:
        for item in st.session_state.historico:
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
        if st.button("Limpar", type="secondary"):
            st.session_state.historico = []
            st.rerun()

    st.markdown('<div class="vr-lbl" style="margin-top:1.5rem">Sobre o modelo</div>', unsafe_allow_html=True)
    st.markdown('<p style="font-size:0.7rem;color:#94A3B8;line-height:1.6">VGG16 treinado no dataset RSNA Pediatric Bone Age Challenge. Autocrop automático aplicado antes da inferência.</p>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
