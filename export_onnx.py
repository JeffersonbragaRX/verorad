"""
export_onnx.py — Exporta o modelo PyTorch para ONNX e verifica paridade.

Uso:
    python export_onnx.py --checkpoint bone_age_v2_best.pt --output bone_age_v2.onnx

O script inclui o teste de paridade: roda 10 amostras no modelo PyTorch e no
ONNX e aborta se a diferença for > 0.5 mês (em qualquer amostra).
"""
import argparse
import json
import numpy as np
import torch
import onnx
import onnxruntime as ort

from train import BoneAgeModel
from preprocess import IMG_SIZE


def export(checkpoint_path: str, output_path: str, opset: int = 17) -> None:
    ckpt = torch.load(checkpoint_path, map_location="cpu")
    backbone = ckpt.get("backbone", "convnextv2_tiny.fcmae_ft_in22k_in1k_384")
    stats = ckpt["stats"]

    model = BoneAgeModel(backbone)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    dummy_img  = torch.randn(1, 3, IMG_SIZE, IMG_SIZE)
    dummy_meta = torch.randn(1, 2)

    torch.onnx.export(
        model,
        (dummy_img, dummy_meta),
        output_path,
        opset_version=opset,
        input_names=["image", "meta"],
        output_names=["bone_age_norm"],
        dynamic_axes={
            "image": {0: "batch"},
            "meta":  {0: "batch"},
            "bone_age_norm": {0: "batch"},
        },
        do_constant_folding=True,
    )

    # Verificar modelo ONNX
    onnx_model = onnx.load(output_path)
    onnx.checker.check_model(onnx_model)
    print(f"ONNX exportado e validado: {output_path}  (opset {opset})")

    # ── Teste de paridade PyTorch ↔ ONNX ──
    sess = ort.InferenceSession(output_path, providers=["CPUExecutionProvider"])
    n_samples = 10
    imgs  = torch.randn(n_samples, 3, IMG_SIZE, IMG_SIZE)
    metas = torch.randn(n_samples, 2)

    # Desnormalizar usando stats do treino para reportar em meses
    def denorm(x_norm):
        return np.clip(x_norm * stats["boneage_std"] + stats["boneage_mean"], 0, 228)

    diffs = []
    with torch.no_grad():
        for i in range(n_samples):
            img_i  = imgs[i:i+1]
            meta_i = metas[i:i+1]

            pt_out   = model(img_i, meta_i).numpy()[0]
            onnx_out = sess.run(None, {
                "image": img_i.numpy(),
                "meta":  meta_i.numpy(),
            })[0][0]

            diff = abs(denorm(pt_out) - denorm(onnx_out))
            diffs.append(diff)

    max_diff = max(diffs)
    print(f"Paridade PyTorch ↔ ONNX — diferença máxima: {max_diff:.4f} meses")
    if max_diff > 0.5:
        raise RuntimeError(
            f"FALHA de paridade: diferença {max_diff:.4f}m > 0.5m. "
            "Verifique se o preprocessing é idêntico no treino e na inferência."
        )
    print("Teste de paridade PASSOU.")

    # Salvar stats junto (usadas pelo inference.py)
    stats_out = output_path.replace(".onnx", "_stats.json")
    with open(stats_out, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Stats salvas em: {stats_out}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="bone_age_v2_best.pt")
    parser.add_argument("--output",     default="bone_age_v2.onnx")
    parser.add_argument("--opset",      type=int, default=17)
    args = parser.parse_args()
    export(args.checkpoint, args.output, args.opset)


if __name__ == "__main__":
    main()
