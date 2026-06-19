"""
preprocess.py — Módulo único de pré-processamento VeroRad v2.
ESTA FUNÇÃO É USADA IDENTICAMENTE NO TREINO E NA INFERÊNCIA.
Não reescreva a lógica em outro lugar — importe daqui.
"""
import json
import numpy as np
import cv2
from PIL import Image

# Dimensão de entrada do backbone
IMG_SIZE = 384

# Média/desvio ImageNet (3 canais) — backbone ConvNeXt V2 pré-treinado
PIXEL_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
PIXEL_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

STATS_FILE = "preprocess_stats.json"


def load_stats(path: str = STATS_FILE) -> dict:
    """Carrega média/desvio do target e da idade cronológica salvos no treino."""
    with open(path) as f:
        return json.load(f)


def save_stats(stats: dict, path: str = STATS_FILE) -> None:
    with open(path, "w") as f:
        json.dump(stats, f, indent=2)


def _clahe_rgb(img_np: np.ndarray) -> np.ndarray:
    """Aplica CLAHE no canal L (LAB) para equalização de contraste radiográfico."""
    lab = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)


def preprocess(
    img,
    sexo: int,
    idade_cron_meses: float,
    stats: dict | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Pré-processa imagem + metadados para entrada no modelo.

    Parâmetros
    ----------
    img : PIL.Image ou np.ndarray (H×W×3, uint8)
        Radiografia já em RGB.
    sexo : int
        0 = feminino, 1 = masculino  (convenção do dataset RSNA).
    idade_cron_meses : float
        Idade cronológica em meses.
    stats : dict ou None
        Dict com chaves 'idade_cron_mean', 'idade_cron_std' para normalização.
        Se None, a idade cronológica é passada sem normalização (usar só no EDA).

    Retorna
    -------
    img_tensor : np.ndarray  shape (3, IMG_SIZE, IMG_SIZE), float32
        Imagem normalizada, pronta para o modelo (CHW).
    meta_tensor : np.ndarray  shape (2,), float32
        [sexo_float, idade_cron_normalizada]
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

    # 4. Normalização de pixel → float32 em [0,1] → ImageNet stats
    img = img.astype(np.float32) / 255.0
    img = (img - PIXEL_MEAN) / PIXEL_STD          # HWC
    img = np.transpose(img, (2, 0, 1))             # CHW

    # 5. Metadados
    sexo_f = float(sexo)
    if stats is not None:
        ic_norm = (idade_cron_meses - stats["idade_cron_mean"]) / (stats["idade_cron_std"] + 1e-8)
    else:
        ic_norm = float(idade_cron_meses)
    meta = np.array([sexo_f, ic_norm], dtype=np.float32)

    return img.astype(np.float32), meta
