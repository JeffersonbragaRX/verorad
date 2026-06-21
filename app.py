import streamlit as st
import numpy as np
import requests
import os
import json
import onnxruntime as ort
from PIL import Image
from datetime import datetime
from streamlit_paste_button import paste_image_button
from atlas import get_atlas
from preprocess import preprocess, load_stats

try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

MODEL_V2_FILENAME = "bone_age_v2.onnx"
STATS_V2_FILENAME = "bone_age_v2_stats.json"
MODEL_V2_URL  = "https://huggingface.co/Jeffersonbraga/verorad-bone-age/resolve/main/bone_age_v2.onnx"
STATS_V2_URL  = "https://huggingface.co/Jeffersonbraga/verorad-bone-age/resolve/main/bone_age_v2_stats.json"


def _hf_headers():
    token = None
    try:
        token = st.secrets.get("HF_TOKEN", None)
    except Exception:
        token = None
    if not token:
        token = os.environ.get("HF_TOKEN", None)
    return {"Authorization": f"Bearer {token}"} if token else {}


def _download_file(url, dest, label):
    with requests.get(url, stream=True, headers=_hf_headers()) as r:
        r.raise_for_status()
        total = int(r.headers.get('content-length', 0))
        downloaded = 0
        progress = st.progress(0, text=f"Baixando {label}...")
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    progress.progress(int(downloaded/total*100), text=f"Baixando {label}... {int(downloaded/total*100)}%")
        progress.empty()


@st.cache_resource
def carregar_modelo():
    with st.spinner("Verificando modelo..."):
        if not os.path.exists(MODEL_V2_FILENAME):
            _download_file(MODEL_V2_URL, MODEL_V2_FILENAME, "modelo v2")
        if os.path.getsize(MODEL_V2_FILENAME) < 100_000:
            os.remove(MODEL_V2_FILENAME)
            raise RuntimeError("Arquivo ONNX corrompido ou token invalido.")
        if not os.path.exists(STATS_V2_FILENAME):
            _download_file(STATS_V2_URL, STATS_V2_FILENAME, "stats")
    session = ort.InferenceSession(MODEL_V2_FILENAME, providers=["CPUExecutionProvider"])
    stats = load_stats(STATS_V2_FILENAME)
    return session, stats


def autocrop(img):
    """
    Isola UMA mao. Busca pixels de tecido/osso (faixa 35-250), ignorando
    fundo preto E moldura branca. Se houver duas maos, usa a da esquerda.
    Em qualquer erro, retorna a imagem original.
    """
    if not _HAS_CV2:
        return _autocrop_legado(img)
    try:
        rgb = np.array(img.convert("RGB"))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape

        # Mascara: tecido/osso = nem fundo preto (<35) nem branco de moldura (>250)
        mask = ((gray > 35) & (gray < 250)).astype(np.uint8) * 255

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=3)

        num, labels, stats_cc, cent = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if num <= 1:
            return _autocrop_legado(img)

        area_total = h * w
        comps = []
        for i in range(1, num):
            comps.append((i, stats_cc[i, cv2.CC_STAT_AREA]))
        comps.sort(key=lambda t: t[1], reverse=True)

        grandes = [c for c in comps if c[1] > area_total * 0.06]
        if len(grandes) == 0:
            return _autocrop_legado(img)

        if len(grandes) >= 2:
            g0, g1 = grandes[0][0], grandes[1][0]
            escolhido = g0 if cent[g0][0] <= cent[g1][0] else g1
        else:
            escolhido = grandes[0][0]

        x  = stats_cc[escolhido, cv2.CC_STAT_LEFT]
        y  = stats_cc[escolhido, cv2.CC_STAT_TOP]
        bw = stats_cc[escolhido, cv2.CC_STAT_WIDTH]
        bh = stats_cc[escolhido, cv2.CC_STAT_HEIGHT]

        pad_x = max(10, int(bw * 0.05))
        pad_y = max(10, int(bh * 0.05))
        x0 = max(0, x - pad_x)
        y0 = max(0, y - pad_y)
        x1 = min(w, x + bw + pad_x)
        y1 = min(h, y + bh + pad_y)

        return img.crop((x0, y0, x1, y1))
    except Exception:
        return _autocrop_legado(img)


def _autocrop_legado(img):
    try:
        gray = np.array(img.convert('L')).astype(np.float32)
        cantos = [gray[0,0], gray[0,-1], gray[-1,0], gray[-1,-1]]
        fundo_escuro = sum(c < 100 for c in cantos) >= 3
        mask = gray > 20 if fundo_escuro else gray < 235
        rows, cols = np.any(mask, axis=1), np.any(mask, axis=0)
        if not rows.any() or not cols.any():
            return img
        rmin, rmax = np.where(rows)[0][[0,-1]]
        cmin, cmax = np.where(cols)[0][[0,-1]]
        h, w = gray.shape
        pad_r = max(8, int((rmax-rmin)*0.03)); pad_c = max(8, int((cmax-cmin)*0.03))
        rmin, rmax = max(0,rmin-pad_r), min(h,rmax+pad_r)
        cmin, cmax = max(0,cmin-pad_c), min(w,cmax+pad_c)
        cropped = img.crop((cmin, rmin, cmax, rmax))
        if cropped.size[0]*cropped.size[1] < img.size[0]*img.size[1]*0.90:
            return cropped
        return img
    except Exception:
        return img


def analisar_imagem(img, sexo_int, idade_cron_meses):
    session, stats = carregar_modelo()
    base = autocrop(img)
    st.session_state.img_crop = base  # guarda o recorte para preview
    img_t, meta_t = preprocess(base, sexo_int, idade_cron_meses, stats=stats)
    img_batch  = img_t[np.newaxis, ...]
    meta_batch = meta_t[np.newaxis, ...]
    out_norm = session.run(None, {"image": img_batch, "meta": meta_batch})[0][0]
    bone_age = float(out_norm) * stats["boneage_std"] + stats["boneage_mean"]
    bone_age = float(np.clip(bone_age, 0, 228))
    anos = int(bone_age // 12)
    meses = int(round(bone_age % 12))
    if meses == 12:
        anos += 1; meses = 0
    return anos, meses, bone_age


def gerar_laudo(anos, meses, sexo, ic_meses):
    sexo_txt = "masculino" if sexo == "Masculino" else "feminino"
    conc = ""
    if ic_meses is not None:
        diff = (anos*12+meses) - ic_meses
        if abs(diff) <= 12:
            conc = " Idade ossea compativel com a idade cronologica."
        elif diff > 12:
            conc = f" Idade ossea avancada em relacao a cronologica (+{abs(diff)} meses)."
        else:
            conc = f" Idade ossea atrasada em relacao a cronologica (-{abs(diff)} meses)."
    return (
        f"Radiografia de mao e punho esquerdos do sexo {sexo_txt}. "
        f"A avaliacao automatizada da maturacao esqueletica por IA estima a idade ossea "
        f"em aproximadamente {anos} anos e {meses} meses.{conc} "
        f"Resultado gerado por sistema de auxilio diagnostico - correlacionar com dados clinicos."
    )


def render_timeline(io_meses, ic_meses=None):
    x0, x1, mid = 38, 562, 56
    span = x1 - x0
    max_m = 216
    def mx(m): return x0 + max(0, min(1, m/max_m)) * span
    io_x = mx(io_meses)
    ticks = ""
    for yr in range(0, 19, 2):
        tx = mx(yr*12)
        ticks += f'<line x1="{tx:.1f}" y1="{mid-4}" x2="{tx:.1f}" y2="{mid+4}" stroke="#D1D5DB" stroke-width="1"/>'
        ticks += f'<text x="{tx:.1f}" y="{mid+18}" font-size="8" fill="#9CA3AF" text-anchor="middle" font-family="JetBrains Mono, monospace">{yr}</text>'
    gap = ""
    ic_marker = ""
    if ic_meses is not None:
        ic_x = mx(ic_meses)
        lo, hi = sorted([io_x, ic_x])
        gap = f'<rect x="{lo:.1f}" y="{mid-6}" width="{(hi-lo):.1f}" height="12" fill="#1D4ED8" opacity="0.10" rx="2"/>'
        ic_marker = (
            f'<line x1="{ic_x:.1f}" y1="{mid-9}" x2="{ic_x:.1f}" y2="{mid+9}" stroke="#94A3B8" stroke-width="1.5" stroke-dasharray="3,2"/>'
            f'<circle cx="{ic_x:.1f}" cy="{mid}" r="3.5" fill="#fff" stroke="#94A3B8" stroke-width="1.5"/>'
            f'<text x="{ic_x:.1f}" y="{mid+30}" font-size="7.5" fill="#94A3B8" text-anchor="middle" font-family="Inter">IC</text>'
        )
    return (
        f'<svg viewBox="0 0 600 78" style="width:100%;height:auto" xmlns="http://www.w3.org/2000/svg">'
        f'<line x1="{x0}" y1="{mid}" x2="{x1}" y2="{mid}" stroke="#E5E7EB" stroke-width="2" stroke-linecap="round"/>'
        f'{ticks}{gap}{ic_marker}'
        f'<line x1="{io_x:.1f}" y1="{mid-13}" x2="{io_x:.1f}" y2="{mid+13}" stroke="#1D4ED8" stroke-width="2"/>'
        f'<circle cx="{io_x:.1f}" cy="{mid}" r="5" fill="#1D4ED8"/>'
        f'<text x="{io_x:.1f}" y="{mid-19}" font-size="8.5" fill="#1D4ED8" text-anchor="middle" font-weight="600" font-family="Inter">IO</text>'
        f'<text x="{x0}" y="14" font-size="8" fill="#9CA3AF" font-family="Inter" letter-spacing="0.1em">MATURACAO ESQUELETICA . ANOS</text>'
        f'</svg>'
    )

st.set_page_config(page_title="VeroRad | Bone Age AI", page_icon="x", layout="wide")

for k, v in [("historico", []), ("img_raw", None), ("resultado", None), ("img_crop", None)]:
    if k not in st.session_state:
        st.session_state[k] = v

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
*, html, body { font-family: 'Inter', sans-serif !important; }
.stApp { background: #F4F5F7 !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 !important; max-width: 100% !important; }
@keyframes fadeUp { from { opacity:0; transform: translateY(8px); } to { opacity:1; transform:none; } }
.vr-top { background:#fff; border-bottom:1px solid #E5E7EB; padding:0 2rem; height:54px; display:flex; align-items:center; justify-content:space-between; }
.vr-logo { font-family:'Space Grotesk',sans-serif !important; font-size:1.15rem; font-weight:700; color:#0F1115; letter-spacing:-0.02em; }
.vr-logo em { color:#1D4ED8; font-style:normal; }
.vr-tag { font-size:0.62rem; color:#9CA3AF; letter-spacing:0.16em; text-transform:uppercase; margin-left:12px; }
.vr-online { display:flex; align-items:center; gap:7px; font-size:0.7rem; font-weight:500; color:#059669; background:#ECFDF5; padding:5px 13px; border-radius:99px; border:1px solid #A7F3D0; }
.vr-online::before { content:''; width:6px; height:6px; border-radius:50%; background:#059669; }
.vr-panel { background:#fff; border:1px solid #E5E7EB; border-radius:14px; padding:1.4rem 1.6rem; box-shadow:0 1px 2px rgba(16,17,21,0.04); margin-bottom:1rem; animation:fadeUp 0.45s cubic-bezier(0.22,1,0.36,1); }
.vr-lbl { font-size:0.6rem; font-weight:600; color:#9CA3AF; letter-spacing:0.14em; text-transform:uppercase; margin-bottom:0.65rem; }
.vr-result-row { display:flex; align-items:flex-start; justify-content:space-between; }
.vr-age { font-family:'Space Grotesk',sans-serif !important; font-size:3.6rem; font-weight:600; color:#0F1115; line-height:0.9; letter-spacing:-0.04em; }
.vr-age span { font-size:1.3rem; font-weight:400; color:#9CA3AF; letter-spacing:0; }
.vr-meta { font-size:0.68rem; color:#9CA3AF; font-family:'JetBrains Mono',monospace; margin-top:6px; }
.vr-badge { padding:6px 13px; border-radius:7px; font-size:0.74rem; font-weight:600; white-space:nowrap; }
.badge-ok { background:#ECFDF5; color:#15803D; border:1px solid #A7F3D0; }
.badge-av { background:#FFF7ED; color:#C2410C; border:1px solid #FED7AA; }
.badge-at { background:#EFF6FF; color:#1D4ED8; border:1px solid #BFDBFE; }
.vr-timeline { margin:1.4rem 0 0.5rem; padding-top:1.2rem; border-top:1px solid #F3F4F6; }
.vr-laudo { background:#F8FAFC; border-left:3px solid #1D4ED8; border-radius:0 8px 8px 0; padding:0.9rem 1rem; font-family:'JetBrains Mono',monospace; font-size:0.74rem; color:#334155; line-height:1.7; position:relative; }
.vr-copy-btn { position:absolute; top:8px; right:8px; background:#fff; border:1px solid #E2E8F0; color:#64748B; font-size:0.64rem; font-weight:600; padding:4px 9px; border-radius:5px; cursor:pointer; font-family:'Inter',sans-serif; }
.vr-copy-btn:hover { background:#1D4ED8; color:#fff; border-color:#1D4ED8; }
.vr-atlas { background:#fff; border:1px solid #E5E7EB; border-radius:12px; padding:1.1rem 1.4rem; }
.vr-atlas-title { font-size:0.68rem; font-weight:600; color:#1D4ED8; letter-spacing:0.08em; text-transform:uppercase; margin-bottom:0.85rem; }
.vr-atlas-section { font-size:0.6rem; font-weight:600; color:#6B7280; letter-spacing:0.1em; text-transform:uppercase; margin-bottom:0.5rem; }
.vr-atlas-item { font-size:0.77rem; color:#4B5563; line-height:1.5; padding:0.2rem 0 0.2rem 0.8rem; border-left:2px solid #EEF0F3; margin-bottom:0.25rem; }
.vr-atlas-ref { font-size:0.6rem; color:#D1D5DB; font-family:'JetBrains Mono',monospace; margin-top:0.7rem; }
.vr-notice { background:#FFFBEB; border:1px solid #FDE68A; border-radius:7px; padding:0.6rem 0.9rem; font-size:0.69rem; color:#92400E; }
.vr-hint { background:#EFF6FF; border:1px solid #DBEAFE; border-radius:9px; padding:0.75rem 0.95rem; font-size:0.73rem; color:#1E40AF; line-height:1.75; margin-bottom:0.75rem; }
.vr-hint kbd { background:#DBEAFE; padding:1px 6px; border-radius:4px; font-family:'JetBrains Mono',monospace; font-size:0.67rem; }
.vr-hist { background:#fff; border:1px solid #F3F4F6; border-radius:9px; padding:0.6rem 0.85rem; margin-bottom:0.45rem; display:flex; justify-content:space-between; align-items:center; }
.vr-hist-age { font-family:'Space Grotesk',sans-serif !important; font-size:0.92rem; font-weight:600; color:#0F1115; }
.vr-hist-sub { font-size:0.63rem; color:#9CA3AF; font-family:'JetBrains Mono',monospace; }
.badge-m { background:#EFF6FF; color:#1D4ED8; font-size:0.58rem; font-weight:700; padding:2px 7px; border-radius:4px; }
.badge-f { background:#FDF4FF; color:#9333EA; font-size:0.58rem; font-weight:700; padding:2px 7px; border-radius:4px; }
.vr-ph { background:#FAFBFC; border:1.5px dashed #D1D5DB; border-radius:14px; height:260px; display:flex; flex-direction:column; align-items:center; justify-content:center; color:#CBD5E1; gap:12px; }
div[data-testid="stSelectbox"] label, div[data-testid="stTextInput"] label, div[data-testid="stNumberInput"] label, div[data-testid="stFileUploader"] label { display:none !important; }
.stButton > button { border-radius:9px !important; font-weight:600 !important; font-size:0.8rem !important; width:100% !important; height:38px !important; }
.stButton > button[kind="secondary"] { background:#F9FAFB !important; color:#6B7280 !important; border:1px solid #E5E7EB !important; }
div[data-testid="stFileUploader"] { padding:0.25rem !important; }
div[data-testid="stImage"] img { border-radius:10px; border:1px solid #E5E7EB; }
.vr-field-lbl { font-size:0.62rem; font-weight:600; color:#6B7280; margin-bottom:3px; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="vr-top">
    <div><span class="vr-logo">Vero<em>Rad</em></span><span class="vr-tag">Bone Age AI</span></div>
    <div class="vr-online">Sistema operacional</div>
</div>
""", unsafe_allow_html=True)

col_l, col_m, col_r = st.columns([1, 1.05, 1.75], gap="medium")

with col_l:
    st.markdown('<div style="padding:1.1rem 0.5rem 0">', unsafe_allow_html=True)
    st.markdown('<div class="vr-lbl">Dados do paciente</div>', unsafe_allow_html=True)
    sexo = st.selectbox("sexo", ["Masculino", "Feminino"], label_visibility="collapsed")

    st.markdown('<div class="vr-field-lbl">Idade cronologica</div>', unsafe_allow_html=True)
    c_anos, c_meses = st.columns(2)
    with c_anos:
        anos_ic = st.number_input("Anos", min_value=0, max_value=20, value=0, step=1, format="%d", key="anos_ic")
        st.markdown('<div style="font-size:0.55rem;color:#9CA3AF;text-align:center;margin-top:-8px">ANOS</div>', unsafe_allow_html=True)
    with c_meses:
        meses_ic = st.number_input("Meses", min_value=0, max_value=11, value=0, step=1, format="%d", key="meses_ic")
        st.markdown('<div style="font-size:0.55rem;color:#9CA3AF;text-align:center;margin-top:-8px">MESES</div>', unsafe_allow_html=True)

    st.markdown('<div class="vr-hint"><b>Como capturar:</b><br>1. No PACS, maximize a radiografia<br>2. Pressione <kbd>Win + Shift + S</kbd><br>3. Selecione a mao e o punho<br>4. Clique em Colar abaixo</div>', unsafe_allow_html=True)

    st.markdown('<div class="vr-lbl">Radiografia</div>', unsafe_allow_html=True)
    paste_result = paste_image_button(label="Colar imagem")
    upload = st.file_uploader("up", type=["png","jpg","jpeg"], label_visibility="collapsed")

    nova_img = None
    if paste_result and paste_result.image_data:
        nova_img = paste_result.image_data.convert("RGB")
    elif upload:
        nova_img = Image.open(upload).convert("RGB")
    if nova_img is not None:
        st.session_state.img_raw = nova_img
        st.session_state.resultado = None
        st.session_state.img_crop = None

    if st.session_state.historico:
        st.markdown('<div class="vr-lbl" style="margin-top:1.5rem">Historico da sessao</div>', unsafe_allow_html=True)
        for item in st.session_state.historico[:8]:
            bc = "badge-m" if item["sexo"]=="Masculino" else "badge-f"
            bl = "M" if item["sexo"]=="Masculino" else "F"
            st.markdown(f'<div class="vr-hist"><div><div class="vr-hist-age">{item["anos"]}a {item["meses"]:02d}m</div><div class="vr-hist-sub">{item["meses_totais"]:.1f}m . {item["horario"]}</div></div><span class="{bc}">{bl}</span></div>', unsafe_allow_html=True)
        if st.button("Limpar historico", type="secondary"):
            st.session_state.historico = []
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

with col_m:
    st.markdown('<div style="padding:1.1rem 0.5rem 0">', unsafe_allow_html=True)
    st.markdown('<div class="vr-lbl">Radiografia carregada</div>', unsafe_allow_html=True)
    if st.session_state.img_raw:
        st.image(st.session_state.img_raw, use_container_width=True)
        if st.session_state.get("img_crop") is not None:
            st.markdown('<div class="vr-lbl" style="margin-top:1rem">Recorte usado pela IA (autocrop)</div>', unsafe_allow_html=True)
            st.image(st.session_state.img_crop, use_container_width=True)
    else:
        st.markdown('<div class="vr-ph"><div style="font-size:0.78rem">Nenhuma imagem carregada</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with col_r:
    st.markdown('<div style="padding:1.1rem 0.5rem 0">', unsafe_allow_html=True)

    # Idade cronologica em meses (None se ambos forem 0)
    total_ic = int(anos_ic)*12 + int(meses_ic)
    ic_meses = total_ic if total_ic > 0 else None

    sexo_int = 1 if sexo == "Masculino" else 0
    ic_para_modelo = ic_meses if ic_meses is not None else 120.0

    if st.session_state.img_raw and st.session_state.resultado is None:
        try:
            with st.spinner("Analisando..."):
                st.session_state.resultado = analisar_imagem(st.session_state.img_raw, sexo_int, ic_para_modelo)
                anos, meses, idm = st.session_state.resultado
                if not st.session_state.historico or st.session_state.historico[0].get("meses_totais") != idm:
                    st.session_state.historico.insert(0, {"anos":anos,"meses":meses,"sexo":sexo,"horario":datetime.now().strftime("%H:%M"),"meses_totais":idm})
                    st.session_state.historico = st.session_state.historico[:20]
        except Exception as e:
            st.error(f"Erro: {e}")

    if st.session_state.resultado:
        anos, meses, idade_meses = st.session_state.resultado
        badge_html = ""
        if ic_meses is not None:
            diff = (anos*12+meses) - ic_meses
            if abs(diff) <= 12:
                badge_html = '<span class="vr-badge badge-ok">Compativel com IC</span>'
            elif diff > 12:
                badge_html = f'<span class="vr-badge badge-av">Avancada +{abs(diff)}m</span>'
            else:
                badge_html = f'<span class="vr-badge badge-at">Atrasada -{abs(diff)}m</span>'

        laudo = gerar_laudo(anos, meses, sexo, ic_meses)
        timeline_svg = render_timeline(idade_meses, ic_meses)

        result_html = '<div class="vr-panel"><div class="vr-result-row"><div><div class="vr-age">' + str(anos) + '<span>a </span>' + f'{meses:02d}' + '<span>m</span></div><div class="vr-meta">' + f'{idade_meses:.2f}' + ' meses . ' + sexo + ' . autocrop ativo</div></div>' + badge_html + '</div><div class="vr-timeline">' + timeline_svg + '</div></div>'
        st.markdown(result_html, unsafe_allow_html=True)

        laudo_html = '<div class="vr-panel" style="padding-top:1.1rem"><div class="vr-lbl">Texto para laudo</div><div class="vr-laudo"><span id="laudo-txt">' + laudo + '</span><button class="vr-copy-btn" onclick="navigator.clipboard.writeText(document.getElementById(\'laudo-txt\').innerText)">Copiar</button></div></div>'
        st.markdown(laudo_html, unsafe_allow_html=True)

        atlas = get_atlas(idade_meses)
        carpo_html = "".join(f'<div class="vr-atlas-item">{i}</div>' for i in atlas["carpo"])
        epif_html  = "".join(f'<div class="vr-atlas-item">{i}</div>' for i in atlas["epifises"])
        atlas_html = '<div class="vr-atlas"><div class="vr-atlas-title">Atlas Greulich &amp; Pyle - ' + atlas['titulo'] + '</div><div style="display:flex;gap:1.5rem"><div style="flex:1"><div class="vr-atlas-section">Carpo</div>' + carpo_html + '</div><div style="flex:1"><div class="vr-atlas-section">Epifises</div>' + epif_html + '</div></div><div class="vr-atlas-ref">' + atlas['referencia_gp'] + '</div></div>'
        st.markdown(atlas_html, unsafe_allow_html=True)
        st.markdown('<div class="vr-notice" style="margin-top:0.75rem">Ferramenta de auxilio diagnostico. Nao substitui avaliacao do radiologista responsavel.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="vr-panel" style="opacity:0.45"><div class="vr-age" style="color:#D1D5DB">--<span>a </span>--<span>m</span></div><div style="height:90px;background:#F4F5F7;border-radius:9px;display:flex;align-items:center;justify-content:center;color:#9CA3AF;font-size:0.8rem;margin-top:0.75rem">Aguardando radiografia</div></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
