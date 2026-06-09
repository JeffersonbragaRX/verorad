import streamlit as st
import numpy as np
import requests
import os
import onnxruntime as ort
from PIL import Image
from datetime import datetime
from streamlit_paste_button import paste_image_button
from atlas import get_atlas

# --- CONFIGURAÇÃO DO MODELO ---
MODEL_FILENAME = "bone_age_model.onnx"
MODEL_URL = "https://huggingface.co/Jeffersonbraga/verorad-bone-age/resolve/main/bone_age_model.onnx"

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="VeroRad | Bone Age AI", page_icon="🩻", layout="wide", initial_sidebar_state="collapsed")

# --- CSS PREMIUM (Design System Clínico) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="st-"] { font-family: 'Inter', sans-serif !important; }
    .stApp { background-color: #F3F4F6 !important; } /* Fundo cinza super suave */
    
    /* Esconder elementos padrão do Streamlit */
    #MainMenu, header, footer { visibility: hidden; }
    .block-container { padding-top: 1rem !important; padding-bottom: 0 !important; max-width: 95% !important; }
    
    /* Topbar Premium */
    .vr-topbar { background: #FFFFFF; border-bottom: 1px solid #E5E7EB; padding: 16px 32px; display: flex; align-items: center; justify-content: space-between; border-radius: 12px; margin-bottom: 24px; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05); }
    .vr-logo-text { font-size: 1.25rem; font-weight: 700; color: #111827; letter-spacing: -0.025em; }
    .vr-logo-text em { color: #2563EB; font-style: normal; }
    .vr-status { display: flex; align-items: center; gap: 8px; font-size: 0.75rem; font-weight: 500; color: #059669; background: #D1FAE5; padding: 4px 12px; border-radius: 9999px; }
    .vr-status::before { content: ''; display: block; width: 6px; height: 6px; border-radius: 50%; background: #059669; }

    /* Cards e Containers */
    .vr-panel { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; padding: 24px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); margin-bottom: 16px; }
    .vr-section-title { font-size: 0.875rem; font-weight: 600; color: #6B7280; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 16px; }
    
    /* Resultados */
    .vr-result-hero { display: flex; align-items: center; justify-content: space-between; padding-bottom: 16px; border-bottom: 1px solid #F3F4F6; margin-bottom: 16px; }
    .vr-age-display { font-size: 3.5rem; font-weight: 700; color: #111827; line-height: 1; letter-spacing: -0.05em; }
    .vr-age-display span { font-size: 1.5rem; font-weight: 500; color: #6B7280; }
    
    /* Badges */
    .vr-badge { padding: 6px 12px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; }
    .badge-ok { background: #F0FDF4; color: #15803D; border: 1px solid #BBF7D0; }
    .badge-av { background: #FEF2F2; color: #B45309; border: 1px solid #FECACA; }
    .badge-at { background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; }
    
    /* Laudo */
    .vr-laudo-box { background: #F8FAFC; border-left: 4px solid #3B82F6; padding: 16px; border-radius: 0 8px 8px 0; position: relative; margin-top: 8px; }
    .vr-laudo-text { font-family: 'Inter', monospace; font-size: 0.875rem; color: #334155; line-height: 1.6; }
    .vr-btn-copy { position: absolute; top: 12px; right: 12px; background: white; border: 1px solid #E2E8F0; color: #475569; font-size: 0.75rem; font-weight: 500; padding: 4px 8px; border-radius: 4px; cursor: pointer; transition: all 0.2s; }
    .vr-btn-copy:hover { background: #F1F5F9; color: #0F172A; }
    
    /* Ajustes Streamlit Elements */
    .stButton > button { width: 100%; border-radius: 8px; font-weight: 600; height: 44px; transition: all 0.2s; }
    .stButton > button[kind="primary"] { background-color: #2563EB; border-color: #2563EB; }
    .stButton > button[kind="primary"]:hover { background-color: #1D4ED8; border-color: #1D4ED8; transform: translateY(-1px); box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2); }
    div[data-testid="stFileUploader"] { padding: 0 !important; }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÕES CORE ---
def vgg16_preprocess(img_array):
    img = img_array.astype(np.float32)[:, :, ::-1]
    img[:, :, 0] -= 103.939; img[:, :, 1] -= 116.779; img[:, :, 2] -= 123.68
    return img

@st.cache_resource
def carregar_modelo():
    if not os.path.exists(MODEL_FILENAME):
        with st.spinner("Sincronizando IA clínica..."):
            response = requests.get(MODEL_URL, stream=True)
            response.raise_for_status()
            with open(MODEL_FILENAME, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536): f.write(chunk)
    return ort.InferenceSession(MODEL_FILENAME)

def autocrop(img):
    gray = np.array(img.convert('L')).astype(np.float32)
    cantos = [gray[0,0], gray[0,-1], gray[-1,0], gray[-1,-1]]
    fundo_escuro = sum(c < 100 for c in cantos) >= 3
    mask = gray > 20 if fundo_escuro else gray < 235
    rows, cols = np.any(mask, axis=1), np.any(mask, axis=0)
    if not rows.any() or not cols.any(): return img
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    h, w = gray.shape
    pad_r, pad_c = max(8, int((rmax - rmin) * 0.03)), max(8, int((cmax - cmin) * 0.03))
    rmin, rmax = max(0, rmin-pad_r), min(h, rmax+pad_r)
    cmin, cmax = max(0, cmin-pad_c), min(w, cmax+pad_c)
    cropped = img.crop((cmin, rmin, cmax, rmax))
    return cropped if (cropped.size[0] * cropped.size[1]) < (img.size[0] * img.size[1] * 0.90) else img

def analisar_imagem(img):
    session = carregar_modelo()
    img_crop = autocrop(img)
    img_resized = img_crop.resize((384, 384), Image.LANCZOS)
    img_batch = np.expand_dims(vgg16_preprocess(np.array(img_resized).astype(np.float32)), axis=0)
    resultado = session.run(None, {session.get_inputs()[0].name: img_batch})
    idade_meses = max(0, float(resultado[0][0][0]))
    anos = int(idade_meses // 12)
    meses = int(round(idade_meses % 12))
    if meses == 12: anos += 1; meses = 0
    return anos, meses, idade_meses

def gerar_laudo(anos, meses, sexo, idade_cron):
    sexo_txt = "masculino" if sexo == "Masculino" else "feminino"
    concordancia_txt = ""
    badge_html = ""
    
    if idade_cron and "," in idade_cron:
        try:
            partes = idade_cron.replace(";",",").split(",")
            ic_anos, ic_meses = int(partes[0].strip()), int(partes[1].strip())
            diff = (anos*12+meses) - (ic_anos*12+ic_meses)
            if abs(diff) <= 12:
                concordancia_txt = " Idade óssea compatível com a idade cronológica."
                badge_html = '<div class="vr-badge badge-ok">✓ Compatível com IC</div>'
            elif diff > 12:
                concordancia_txt = f" Idade óssea avançada em relação à cronológica (+{abs(diff)} meses)."
                badge_html = f'<div class="vr-badge badge-av">↑ Avançada (+{abs(diff)}m)</div>'
            else:
                concordancia_txt = f" Idade óssea atrasada em relação à cronológica (-{abs(diff)} meses)."
                badge_html = f'<div class="vr-badge badge-at">↓ Atrasada (-{abs(diff)}m)</div>'
        except: pass
        
    laudo = f"Radiografia de mão e punho esquerdos do sexo {sexo_txt}. A avaliação automatizada da maturação esquelética por Inteligência Artificial (Modelo VGG16) estima a idade óssea em aproximadamente {anos} anos e {meses} meses.{concordancia_txt} Nota: Resultado gerado por sistema de auxílio diagnóstico, devendo ser correlacionado com os dados clínicos."
    return laudo, badge_html

# --- ESTADO DA SESSÃO E CORREÇÃO DE BUGS ---
if "historico" not in st.session_state: st.session_state.historico = []
if "img_raw" not in st.session_state: st.session_state.img_raw = None
if "resultado" not in st.session_state: st.session_state.resultado = None
if "current_img_hash" not in st.session_state: st.session_state.current_img_hash = None

# --- TOPBAR ---
st.markdown("""
<div class="vr-topbar">
    <div class="vr-logo-text">Vero<em>Rad</em></div>
    <div class="vr-status">Online e Seguro</div>
</div>
""", unsafe_allow_html=True)

# --- LAYOUT PRINCIPAL ---
col_cfg, col_img, col_res = st.columns([1, 1.2, 1.8], gap="large")

# 1. COLUNA: CONFIGURAÇÃO
with col_cfg:
    st.markdown('<div class="vr-section-title">1. Dados do Paciente</div>', unsafe_allow_html=True)
    sexo = st.selectbox("Sexo Biológico", ["Masculino", "Feminino"], label_visibility="collapsed")
    idade_cron = st.text_input("Idade Cron.", placeholder="Idade Cronológica (ex: 8, 6)", label_visibility="collapsed")
    
    st.markdown('<div class="vr-section-title" style="margin-top:24px;">2. Radiografia</div>', unsafe_allow_html=True)
    paste_result = paste_image_button(label="📋 Colar do Clipboard (Win+Shift+S)", key="paste_btn")
    upload = st.file_uploader("Ou arquivo", type=["png","jpg","jpeg"], label_visibility="collapsed")
    
    nova_img = None
    if paste_result and paste_result.image_data: 
        nova_img = paste_result.image_data.convert("RGB")
    elif upload: 
        nova_img = Image.open(upload).convert("RGB")
    
    # Prevenção do Bug de Reset Infinito (usa um hash para saber se a imagem é realmente nova)
    if nova_img is not None:
        img_hash = hash(nova_img.tobytes())
        if st.session_state.current_img_hash != img_hash:
            st.session_state.img_raw = nova_img
            st.session_state.current_img_hash = img_hash
            st.session_state.resultado = None
            st.rerun() # Limpa a interface imediatamente para evitar conflitos DOM

    if st.session_state.historico:
        st.markdown('<div class="vr-section-title" style="margin-top:32px;">Sessão Atual</div>', unsafe_allow_html=True)
        for idx, item in enumerate(st.session_state.historico[:5]):
            st.markdown(f"""
            <div style="background:#FFFFFF; border:1px solid #E5E7EB; padding:10px; border-radius:8px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
                <div><strong style="color:#111827;font-size:0.9rem;">{item['anos']}a {item['meses']:02d}m</strong> <span style="color:#6B7280;font-size:0.75rem;margin-left:4px;">{item['sexo'][0]}</span></div>
                <div style="color:#9CA3AF;font-size:0.7rem;font-family:monospace;">{item['horario']}</div>
            </div>
            """, unsafe_allow_html=True)
        if st.button("Limpar Histórico"):
            st.session_state.historico = []
            st.rerun()

# 2. COLUNA: VISUALIZADOR
with col_img:
    st.markdown('<div class="vr-section-title">Visualizador DICOM/RAW</div>', unsafe_allow_html=True)
    if st.session_state.img_raw:
        # Corrigido o erro do Log (Substituição do use_container_width por width="stretch")
        st.image(st.session_state.img_raw, width="stretch", caption="Imagem pronta para análise")
        
        if st.session_state.resultado is None:
            if st.button("🚀 Processar Análise de IA", type="primary"):
                with st.spinner("Processando..."):
                    st.session_state.resultado = analisar_imagem(st.session_state.img_raw)
                st.rerun() # Essencial para evitar o erro removeChild de Node
    else:
        st.markdown("""
        <div style="background:#F8FAFC; border:2px dashed #CBD5E1; border-radius:12px; height:300px; display:flex; flex-direction:column; align-items:center; justify-content:center; color:#94A3B8;">
            <svg width="48" height="48" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
            <p style="margin-top:16px; font-size:0.875rem; font-weight:500;">Nenhuma imagem carregada</p>
        </div>
        """, unsafe_allow_html=True)

# 3. COLUNA: RESULTADOS E LAUDO
with col_res:
    st.markdown('<div class="vr-section-title">Resultados Clínicos</div>', unsafe_allow_html=True)
    
    if st.session_state.resultado:
        anos, meses, idade_meses = st.session_state.resultado
        laudo_texto, badge_html = gerar_laudo(anos, meses, sexo, idade_cron)
        
        # Guardar no histórico (evitar duplicados)
        if not st.session_state.historico or st.session_state.historico[0].get("meses_totais") != idade_meses:
            st.session_state.historico.insert(0, {"anos": anos, "meses": meses, "sexo": sexo, "horario": datetime.now().strftime("%H:%M"), "meses_totais": idade_meses})
        
        st.markdown(f"""
        <div class="vr-panel">
            <div class="vr-result-hero">
                <div class="vr-age-display">{anos}<span>a</span> {meses:02d}<span>m</span></div>
                {badge_html}
            </div>
            <div style="font-size:0.875rem; color:#6B7280; font-family:monospace; margin-bottom:16px;">
                Métrica exata: {idade_meses:.2f} meses | Modelo VGG16 (Autocrop ativo)
            </div>
            
            <div style="font-weight:600; font-size:0.875rem; color:#111827; margin-bottom:8px;">Sugestão de Laudo</div>
            <div class="vr-laudo-box">
                <div class="vr-laudo-text" id="laudo-text">{laudo_texto}</div>
                <button class="vr-btn-copy" onclick="navigator.clipboard.writeText(document.getElementById('laudo-text').innerText)">
                    Copiar
                </button>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Referências Atlas
        atlas = get_atlas(idade_meses)
        carpo_items = "".join(f'<li style="margin-bottom:4px;">{i}</li>' for i in atlas["carpo"])
        epif_items = "".join(f'<li style="margin-bottom:4px;">{i}</li>' for i in atlas["epifises"])
        
        st.markdown(f"""
        <div class="vr-panel" style="background:#F8FAFC; border:none;">
            <div style="font-weight:600; font-size:0.875rem; color:#111827; margin-bottom:12px;">📚 Referência Literária (Atlas Greulich & Pyle)</div>
            <div style="font-size:0.875rem; color:#475569; margin-bottom:12px;"><strong>Placa de Referência:</strong> {atlas['titulo']}</div>
            <div style="display:flex; gap:24px; font-size:0.8rem; color:#475569;">
                <div style="flex:1;">
                    <strong style="color:#2563EB;">Evolução do Carpo:</strong>
                    <ul style="padding-left:16px; margin-top:8px;">{carpo_items}</ul>
                </div>
                <div style="flex:1;">
                    <strong style="color:#2563EB;">Evolução das Epífises:</strong>
                    <ul style="padding-left:16px; margin-top:8px;">{epif_items}</ul>
                </div>
            </div>
            <div style="font-size:0.7rem; color:#9CA3AF; margin-top:16px; font-family:monospace;">Ref: {atlas['referencia_gp']}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="vr-panel" style="opacity: 0.5; filter: grayscale(1);">
            <div class="vr-result-hero">
                <div class="vr-age-display">--<span>a</span> --<span>m</span></div>
            </div>
            <div style="height:100px; background:#F1F5F9; border-radius:8px; display:flex; align-items:center; justify-content:center; color:#94A3B8; font-size:0.875rem;">
                Resultados aparecerão aqui após a análise
            </div>
        </div>
        """, unsafe_allow_html=True)
