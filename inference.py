"""
inference.py — Inferência via ONNX (VeroRad v2).

Usa o MESMO preprocess() do treino — importado de preprocess.py.

Uso:
    from inference import predict
    result = predict("rx_mao.png", sexo=1, idade_cron_meses=96.0)
    print(result)
"""
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from preprocess import preprocess, load_stats

DEFAULT_MODEL  = "bone_age_v2.onnx"
DEFAULT_STATS  = "bone_age_v2_stats.json"


def _load_session(model_path: str) -> ort.InferenceSession:
    return ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])


def predict(
    img_source,
    sexo: int,
    idade_cron_meses: float,
    model_path: str = DEFAULT_MODEL,
    stats_path: str = DEFAULT_STATS,
) -> dict:
    """
    Estima a idade óssea a partir de imagem + metadados.

    Parâmetros
    ----------
    img_source : str, Path ou PIL.Image
        Caminho para a imagem ou PIL.Image já carregada.
    sexo : int
        0 = feminino, 1 = masculino.
    idade_cron_meses : float
        Idade cronológica em meses.
    model_path : str
        Caminho para o arquivo ONNX.
    stats_path : str
        Caminho para o JSON de estatísticas do treino.

    Retorna
    -------
    dict com:
        bone_age_meses   : float  — idade óssea estimada em meses (clamped 0–228)
        bone_age_anos    : int
        bone_age_meses_r : int    — resto dos meses após anos completos
        delta_meses      : float  — IO − IC em meses (positivo = avançado)
        status           : str    — "avançada" | "atrasada" | "compatível"
    """
    # Carregar imagem se for caminho
    if not isinstance(img_source, Image.Image):
        img_source = Image.open(img_source).convert("RGB")

    stats = load_stats(stats_path)
    img_t, meta_t = preprocess(img_source, sexo, idade_cron_meses, stats=stats)

    # Adicionar dimensão de batch
    img_batch  = img_t[np.newaxis, ...]   # (1, 3, H, W)
    meta_batch = meta_t[np.newaxis, ...]  # (1, 2)

    sess = _load_session(model_path)
    out_norm = sess.run(None, {"image": img_batch, "meta": meta_batch})[0][0]

    # Desnormalizar
    bone_age = float(out_norm) * stats["boneage_std"] + stats["boneage_mean"]
    bone_age = float(np.clip(bone_age, 0, 228))

    anos = int(bone_age // 12)
    meses_r = int(round(bone_age % 12))
    if meses_r == 12:
        anos += 1; meses_r = 0

    delta = bone_age - idade_cron_meses
    if abs(delta) <= 12:
        status = "compatível"
    elif delta > 0:
        status = "avançada"
    else:
        status = "atrasada"

    return {
        "bone_age_meses":   bone_age,
        "bone_age_anos":    anos,
        "bone_age_meses_r": meses_r,
        "delta_meses":      delta,
        "status":           status,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Inferência VeroRad v2")
    parser.add_argument("image", help="Caminho para a radiografia")
    parser.add_argument("--sexo", type=int, required=True, help="0=feminino 1=masculino")
    parser.add_argument("--idade_cron", type=float, required=True, help="Idade cronológica em meses")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--stats", default=DEFAULT_STATS)
    args = parser.parse_args()

    r = predict(args.image, args.sexo, args.idade_cron, args.model, args.stats)
    print(f"Idade óssea : {r['bone_age_anos']}a {r['bone_age_meses_r']:02d}m  ({r['bone_age_meses']:.1f} meses)")
    print(f"Delta IC    : {r['delta_meses']:+.1f} meses — {r['status']}")
