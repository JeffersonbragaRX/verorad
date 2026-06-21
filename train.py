"""
train.py — Treino ConvNeXt V2 + fusão de metadados para idade óssea (VeroRad v2).

Uso:
    python train.py --data_dir /path/to/rsna-bone-age --epochs 30 --batch_size 16

Estrutura esperada do dataset RSNA:
    data_dir/
        boneage-training-dataset/
            <id>.png ...
        train.csv          (colunas: id, boneage, male)
"""
import argparse
import json
import os
import random
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
import timm
from sklearn.model_selection import StratifiedKFold
from PIL import Image
import albumentations as A
from albumentations.pytorch import ToTensorV2

from preprocess import preprocess, save_stats, IMG_SIZE

# ────────────────────────────────────────────────
# Reproducibilidade
# ────────────────────────────────────────────────
SEED = 42

def set_seed(seed=SEED):
    random.seed(seed); np.random.seed(seed)
    torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)

# ────────────────────────────────────────────────
# EDA / guardrails
# ────────────────────────────────────────────────
def run_eda(df: pd.DataFrame) -> None:
    print("\n=== EDA ===")
    print(f"Total de amostras : {len(df)}")
    print(f"Sexo (male=1)     : {df['male'].value_counts().to_dict()}")
    print(f"Boneage (meses)   : min={df['boneage'].min():.1f}  max={df['boneage'].max():.1f}  "
          f"mean={df['boneage'].mean():.1f}  std={df['boneage'].std():.1f}")
    nulos = df[['boneage', 'male']].isnull().sum()
    print(f"Nulos             : {nulos.to_dict()}")

    # Assert de unidade (0–228 meses = 0–19 anos)
    fora = df[(df['boneage'] < 0) | (df['boneage'] > 228)]
    if len(fora) > 0:
        raise ValueError(f"ABORT: {len(fora)} amostras com boneage fora de 0–228 meses! "
                         f"Verifique a unidade (esperado: meses).\n{fora[['id','boneage']].head()}")
    print("Assert de unidade OK (0–228 meses)")
    print("==========\n")

# ────────────────────────────────────────────────
# Dataset
# ────────────────────────────────────────────────
TRAIN_AUG = A.Compose([
    A.Rotate(limit=10, p=0.6),
    A.RandomScale(scale_limit=0.08, p=0.5),
    A.RandomBrightnessContrast(brightness_limit=0.15, contrast_limit=0.15, p=0.5),
    A.GaussNoise(var_limit=(5, 20), p=0.2),
    A.CoarseDropout(max_holes=4, max_height=20, max_width=20, p=0.2),
])


class BoneAgeDataset(Dataset):
    def __init__(self, df: pd.DataFrame, img_dir: str, stats: dict, augment: bool = False):
        self.df = df.reset_index(drop=True)
        self.img_dir = Path(img_dir)
        self.stats = stats
        self.augment = augment

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        img_path = self.img_dir / f"{int(row['id'])}.png"
        img = np.array(Image.open(img_path).convert("RGB"), dtype=np.uint8)

        if self.augment:
            img = TRAIN_AUG(image=img)["image"]

        img_t, meta_t = preprocess(img, int(row['male']), float(row['boneage_ic']),
                                   stats=self.stats)

        target_norm = (float(row['boneage']) - self.stats['boneage_mean']) / self.stats['boneage_std']
        return (
            torch.from_numpy(img_t),
            torch.from_numpy(meta_t),
            torch.tensor(target_norm, dtype=torch.float32),
            torch.tensor(float(row['boneage']), dtype=torch.float32),  # raw, para MAE real
        )

# ────────────────────────────────────────────────
# Modelo
# ────────────────────────────────────────────────
class BoneAgeModel(nn.Module):
    def __init__(self, backbone_name: str = "convnextv2_tiny.fcmae_ft_in22k_in1k_384"):
        super().__init__()
        self.backbone = timm.create_model(
            backbone_name, pretrained=True, num_classes=0, global_pool="avg"
        )
        feat_dim = self.backbone.num_features
        meta_dim = 2  # [sexo, idade_cron_norm]

        self.head = nn.Sequential(
            nn.Linear(feat_dim + meta_dim, 512),
            nn.GELU(),
            nn.Dropout(0.3),
            nn.Linear(512, 128),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(128, 1),
        )

    def forward(self, img: torch.Tensor, meta: torch.Tensor) -> torch.Tensor:
        feats = self.backbone(img)                      # (B, feat_dim)
        x = torch.cat([feats, meta], dim=1)            # (B, feat_dim+2)
        return self.head(x).squeeze(1)                 # (B,)


# ────────────────────────────────────────────────
# Avaliação por subgrupo
# ────────────────────────────────────────────────
def evaluate_subgroups(preds: np.ndarray, targets: np.ndarray, sexos: np.ndarray) -> None:
    mae_global = np.abs(preds - targets).mean()
    print(f"\nMAE GLOBAL : {mae_global:.2f} meses")

    for s, label in [(1, "Masculino"), (0, "Feminino")]:
        mask = sexos == s
        if mask.sum() > 0:
            mae_s = np.abs(preds[mask] - targets[mask]).mean()
            print(f"MAE {label:10s} : {mae_s:.2f} meses  (n={mask.sum()})")

    faixas = [(0, 60, "0–5a"), (60, 120, "5–10a"), (120, 180, "10–15a"), (180, 228, "15+a")]
    for lo, hi, label in faixas:
        mask = (targets >= lo) & (targets < hi)
        if mask.sum() > 0:
            mae_f = np.abs(preds[mask] - targets[mask]).mean()
            print(f"MAE {label:8s} : {mae_f:.2f} meses  (n={mask.sum()})")


# ────────────────────────────────────────────────
# Treino
# ────────────────────────────────────────────────
def train_one_epoch(model, loader, optimizer, scaler, device):
    model.train()
    losses = []
    for img, meta, target_norm, _ in loader:
        img, meta, target_norm = img.to(device), meta.to(device), target_norm.to(device)
        optimizer.zero_grad()
        with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
            pred = model(img, meta)
            loss = nn.functional.l1_loss(pred, target_norm)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        losses.append(loss.item())
    return np.mean(losses)


@torch.no_grad()
def validate(model, loader, stats, device):
    model.eval()
    all_preds, all_targets, all_sexos = [], [], []
    for img, meta, _, target_raw in loader:
        img, meta = img.to(device), meta.to(device)
        with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
            pred_norm = model(img, meta)
        pred_raw = pred_norm.cpu().numpy() * stats['boneage_std'] + stats['boneage_mean']
        pred_raw = np.clip(pred_raw, 0, 228)
        all_preds.append(pred_raw)
        all_targets.append(target_raw.numpy())
        all_sexos.append(meta[:, 0].cpu().numpy())
    preds = np.concatenate(all_preds)
    targets = np.concatenate(all_targets)
    sexos = np.concatenate(all_sexos)
    mae = np.abs(preds - targets).mean()
    return mae, preds, targets, sexos


def plot_worst(preds, targets, img_dir, df_subset, n=5):
    """Salva figura com as N piores predições."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib não instalado — pulando plot das piores predições.")
        return

    errors = np.abs(preds - targets)
    worst_idx = np.argsort(errors)[::-1][:n]
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 5))
    for ax, idx in zip(axes, worst_idx):
        row = df_subset.iloc[idx]
        img_path = Path(img_dir) / f"{int(row['id'])}.png"
        img = Image.open(img_path).convert("RGB")
        ax.imshow(img, cmap="gray")
        ax.set_title(
            f"Real: {targets[idx]:.1f}m\nPred: {preds[idx]:.1f}m\nErro: {errors[idx]:.1f}m",
            fontsize=9
        )
        ax.axis("off")
    plt.tight_layout()
    out = "worst_predictions.png"
    plt.savefig(out, dpi=120)
    plt.close()
    print(f"Piores predições salvas em: {out}")


# ────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", required=True, help="Pasta raiz do dataset RSNA")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--backbone", default="convnextv2_tiny.fcmae_ft_in22k_in1k_384")
    parser.add_argument("--checkpoint", default="bone_age_v2_best.pt")
    parser.add_argument("--patience", type=int, default=7)
    args = parser.parse_args()

    set_seed()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # ── Carregar CSV ──
    data_dir = Path(args.data_dir)
    csv_path = data_dir / "train.csv"
    df = pd.read_csv(csv_path)

    # Normalizar nomes de coluna
    df.columns = [c.strip().lower() for c in df.columns]
    assert "boneage" in df.columns, "CSV deve ter coluna 'boneage'"
    assert "male" in df.columns, "CSV deve ter coluna 'male'"
    df["male"] = df["male"].astype(int)
    df["boneage"] = df["boneage"].astype(float)
    df = df.dropna(subset=["boneage", "male"]).reset_index(drop=True)

    # Usar idade óssea como proxy de IC quando IC não está disponível
    # (o modelo aprende o delta; em produção o usuário fornece a IC real)
    df["boneage_ic"] = df["boneage"]  # substitua por coluna de IC real se disponível

    run_eda(df)

    img_dir = data_dir / "boneage-training-dataset"

    # ── Split estratificado ──
    # Estratificar por (sexo × faixa etária)
    faixas = pd.cut(df["boneage"], bins=[0, 60, 120, 180, 229], labels=False)
    strat_key = df["male"].astype(str) + "_" + faixas.astype(str)

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    train_val_idx, test_idx = next(skf.split(df, strat_key))
    df_trainval = df.iloc[train_val_idx].reset_index(drop=True)
    df_test = df.iloc[test_idx].reset_index(drop=True)

    skf2 = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    strat_key2 = (df_trainval["male"].astype(str) + "_" +
                  pd.cut(df_trainval["boneage"], bins=[0, 60, 120, 180, 229], labels=False).astype(str))
    train_idx, val_idx = next(skf2.split(df_trainval, strat_key2))
    df_train = df_trainval.iloc[train_idx].reset_index(drop=True)
    df_val   = df_trainval.iloc[val_idx].reset_index(drop=True)

    print(f"Treino: {len(df_train)}  Val: {len(df_val)}  Test: {len(df_test)}")

    # ── Estatísticas do treino (salvar para uso na inferência) ──
    stats = {
        "boneage_mean":   float(df_train["boneage"].mean()),
        "boneage_std":    float(df_train["boneage"].std()),
        "idade_cron_mean": float(df_train["boneage_ic"].mean()),
        "idade_cron_std":  float(df_train["boneage_ic"].std()),
    }
    save_stats(stats)
    print(f"Stats salvas em preprocess_stats.json: {stats}")

    # ── Datasets / Loaders ──
    ds_train = BoneAgeDataset(df_train, img_dir, stats, augment=True)
    ds_val   = BoneAgeDataset(df_val,   img_dir, stats, augment=False)
    ds_test  = BoneAgeDataset(df_test,  img_dir, stats, augment=False)

    num_workers = min(4, os.cpu_count() or 1)
    dl_train = DataLoader(ds_train, batch_size=args.batch_size, shuffle=True,
                          num_workers=num_workers, pin_memory=True)
    dl_val   = DataLoader(ds_val,   batch_size=args.batch_size, shuffle=False,
                          num_workers=num_workers, pin_memory=True)
    dl_test  = DataLoader(ds_test,  batch_size=args.batch_size, shuffle=False,
                          num_workers=num_workers, pin_memory=True)

    # ── Modelo ──
    model = BoneAgeModel(args.backbone).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    scaler = torch.cuda.amp.GradScaler(enabled=(device.type == "cuda"))

    best_mae = float("inf")
    patience_count = 0

    for epoch in range(1, args.epochs + 1):
        train_loss = train_one_epoch(model, dl_train, optimizer, scaler, device)
        val_mae, _, _, _ = validate(model, dl_val, stats, device)
        scheduler.step()

        print(f"Epoch {epoch:03d}  train_loss={train_loss:.4f}  val_MAE={val_mae:.2f}m")

        if val_mae < best_mae:
            best_mae = val_mae
            patience_count = 0
            torch.save({"model_state": model.state_dict(), "stats": stats,
                        "backbone": args.backbone}, args.checkpoint)
            print(f"  ✓ Melhor checkpoint salvo ({best_mae:.2f}m)")
        else:
            patience_count += 1
            if patience_count >= args.patience:
                print(f"Early stopping (paciência={args.patience})")
                break

    # ── Avaliação final no test set ──
    print("\n=== AVALIAÇÃO NO TEST SET ===")
    ckpt = torch.load(args.checkpoint, map_location=device)
    model.load_state_dict(ckpt["model_state"])
    test_mae, test_preds, test_targets, test_sexos = validate(model, dl_test, stats, device)
    evaluate_subgroups(test_preds, test_targets, test_sexos)

    # ── 5 piores predições ──
    plot_worst(test_preds, test_targets, img_dir, df_test)

    print(f"\nTreino concluído. Checkpoint: {args.checkpoint}")


if __name__ == "__main__":
    main()
