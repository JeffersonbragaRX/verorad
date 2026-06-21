"""
preprocess.py — Modulo unico de pre-processamento VeroRad v2.
ESTA FUNCAO E USADA IDENTICAMENTE NO TREINO E NA INFERENCIA.
Nao reescreva a logica em outro lugar — importe daqui.

Modelo v2: entrada = imagem (512) + sexo apenas (meta_dim=1).
A idade cronologica NAO e usada (removida para evitar data leakage).
"""
import json
import numpy as np
import cv2
from PIL import Image

# Dimensao de entrada do backbone (modelo treinado em 512)
IMG_SIZE = 512

# Media/desvio ImageNet (3 canais) — backbone ConvNeXt V2 pre-treinado
PIXEL_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
PIXEL_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

STATS_FILE = "preprocess_stats.json"


def load_stats(path: str = STATS_FILE) -> dict:
    """Carrega media/desvio do target salvos no treino."""
    with open(path) as f:
        return json.load(f)


def save_stats(stats: dict, path: str = STATS_FILE) -> None:
    with open(path, "w") as f:
        json.dump(stats, f, indent=2)


def _clahe_rgb(img_np: np.ndarray) -> np.ndarray:
    """Aplica CLAHE no canal L (LAB) para equalizacao de contraste radiografico."""
    lab = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)


def preprocess(
    img,
    sexo: int,
    idade_cron_meses: float = 0.0,
    stats: dict | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Pre-processa imagem + metadados para entrada no modelo.

    Parametros
    ----------
    img : PIL.Image ou np.ndarray (HxWx3, uint8)
        Radiografia ja em RGB.
    sexo : int
        0 = feminino, 1 = masculino (convencao do dataset RSNA).
    idade_cron_meses : float
        Ignorado no v2 (mantido na assinatura por compatibilidade).
    stats : dict ou None
        Ignorado para os metadados no v2 (mantido por compatibilidade).

    Retorna
    -------
    img_tensor : np.ndarray  shape (3, IMG_SIZE, IMG_SIZE), float32
        Imagem normalizada, pronta para o modelo (CHW).
    meta_tensor : np.ndarray  shape (1,), float32
        [sexo_float]
    """
    # 1. Garantir ndarray RGB uint8
    if isinstance(img, Image.Image):
        img = np.array(img.convert("RGB"), dtype=np.uint8)
    else:
        img = np.asarray(img, dtype=np.uint8)
        if img.ndim == 2:
            img = np.stack([img] * 3, axis=-1)
        elif img.shape[2] == 1:
            img = np.concatenate([img] * 3, axis=-1)

    # 2. Resize
    img = cv2.resize(img, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_LINEAR)

    # 3. CLAHE
    img = _clahe_rgb(img)

    # 4. Normalizacao de pixel -> float32 em [0,1] -> ImageNet stats
    img = img.astype(np.float32) / 255.0
    img = (img - PIXEL_MEAN) / PIXEL_STD          # HWC
    img = np.transpose(img, (2, 0, 1))             # CHW

    # 5. Metadados — APENAS o sexo (meta_dim=1)
    sexo_f = float(sexo)
    meta = np.array([sexo_f], dtype=np.float32)

    return img.astype(np.float32), meta
