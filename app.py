import streamlit as st
import numpy as np
import requests
import os
import onnxruntime as ort
from PIL import Image
from streamlit_paste_button import paste_image_button

# --- CONFIGURAÇÃO ---
MODEL_URL = "https://docs.google.com/uc?export=download&id=1NYeHyK6Rg9v9paePeyraKCC3dKML6qWr"
MODEL_PATH = "bone_age_model.onnx"

# --- CSS CUSTOMIZADO PARA ESTÉTICA PROFISSIONAL ---
st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    .main-card { 
        background: white; 
        padding: 2rem; 
        border-radius: 15px; 
        box-shadow: 0 4px 15px rgba(0,0,0,0.1); 
    }
    .big-font { font-size: 24px !important; font-weight: bold; color: #1e3a8a; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource
def carregar_ia():
    if not os.path.exists(MODEL_PATH):
        response = requests.get(MODEL_URL, stream=True)
        with open(MODEL_PATH, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
    return ort.InferenceSession(MODEL_PATH)

st.set_page_config(page_title="VeroRad | Análise Clínica", page_icon="🦴")

# --- CABEÇALHO ---
st.title("🦴 VeroRad")
st.subheader("Análise Avançada de Idade Óssea por Inteligência Artificial")
st.markdown("---")

try:
    session = carregar_ia()
    
    # --- ÁREA DE INPUT ---
    with st.container():
        st.markdown('<div class="main-card">', unsafe_allow_html=True)
        col1, col2 = st.columns([1, 1])
        with col1:
            paste_result = paste_image_button(label="📋 Colar Raio-X da Área de Transferência")
        with col2:
            upload = st.file_uploader("Ou carregue ficheiro (JPG/PNG):", type=["png", "jpg", "jpeg"])
        st.markdown('</div>', unsafe_allow_html=True)
    
    img_data = paste_result.image_data if (paste_result and paste_result.image_data) else upload

    if img_data:
        st.markdown("### Pré-visualização do Exame")
        img = Image.open(img_data).convert('RGB')
        st.image(img, use_container_width=True)
        
        if st.button("🚀 Executar Análise Clínica", type="primary"):
            with st.status("Processando imagem via VeroNet...", expanded=True) as status:
                img_arr = np.array(img.resize((384, 384))).astype(np.float32)
                img_arr = np.expand_dims(img_arr, axis=0) / 255.0
                
                input_name = session.get_inputs()[0].name
                resultado = session.run(None, {input_name: img_arr})
                
                idade = float(resultado[0][0][0])
                status.update(label="Análise Concluída!", state="complete")
            
            # --- RESULTADO FINAL ---
            st.success("Resultado da Estimativa")
            st.metric("Idade Óssea Calculada", f"{int(idade//12)} anos e {int(idade%12)} meses")
            st.info("Nota: Este resultado é uma estimativa baseada em IA e deve ser validado por um radiologista.")
            
except Exception as e:
    st.error(f"Erro no sistema: {e}")
