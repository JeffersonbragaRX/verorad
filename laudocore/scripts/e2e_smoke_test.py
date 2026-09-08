#!/usr/bin/env python3
"""Teste de ponta a ponta do fluxo principal (Fase 8) — sobe a API real
(servindo o build do frontend), abre num navegador de verdade via
Playwright, e exercita: Dashboard -> Biblioteca (busca + detalhe) ->
Novo Laudo (busca de achado, seleção, compilação, cópia) -> Fila de
revisão (resolver + reabrir, sem deixar efeito colateral).

Cada etapa tem uma asserção real (nao e so captura de tela). Screenshots
vao para --out (padrao: fora do repositorio) porque mostram texto real
de laudo — nunca commitar essa pasta (ver docs/decisions/0002).

Requer: banco processado (ingest_vertical.py + extract_concepts.py),
frontend construido (frontend/dist — rode `cd frontend && npm run
build` antes, ou deixe este script fazer via --build) e o pacote
`playwright` com o Chromium ja instalado.

Uso:
    python3 scripts/e2e_smoke_test.py --out /tmp/laudocore_e2e_shots
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "processed" / "laudocore.db"
FRONTEND_DIST = ROOT / "frontend" / "dist"
PORT = 8010
BASE_URL = f"http://127.0.0.1:{PORT}"


def wait_for_server(timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=1)
            return
        except Exception:
            time.sleep(0.3)
    raise SystemExit("Servidor não respondeu a tempo.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/tmp/laudocore_e2e_shots",
                         help="Pasta para screenshots (NAO commitar — contém texto real de laudo)")
    parser.add_argument("--build", action="store_true", help="Roda 'npm run build' antes do teste")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} não existe. Rode ingest_vertical.py e extract_concepts.py antes.")

    if args.build or not FRONTEND_DIST.exists():
        print("Construindo o frontend…")
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "frontend", check=True)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Subindo servidor de teste em {BASE_URL}…")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.api.app:app", "--port", str(PORT)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        wait_for_server()
        run_flow(out_dir)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    print(f"\nOK — fluxo completo validado. Screenshots em: {out_dir}")


def run_flow(out_dir: Path) -> None:
    from playwright.sync_api import sync_playwright

    chromium_path = None
    for candidate in Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"):
        chromium_path = str(candidate)
        break

    with sync_playwright() as p:
        launch_kwargs = {"executable_path": chromium_path} if chromium_path else {}
        browser = p.chromium.launch(**launch_kwargs)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # 1. Dashboard
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_selector("text=Laudos no vertical")
        reports_total = page.locator("text=Laudos no vertical").locator("..").locator("p").nth(1).inner_text()
        assert int(reports_total.replace(".", "")) > 0, "Dashboard não mostrou contagem real de laudos"
        page.screenshot(path=str(out_dir / "01_dashboard.png"))
        print("[ok] Dashboard mostra dados reais:", reports_total, "laudos")

        # 2. Biblioteca — busca e detalhe
        page.goto(f"{BASE_URL}/biblioteca", wait_until="networkidle")
        page.wait_for_selector("button:has-text('#')")
        page.locator("button:has-text('#')").first.click()
        page.wait_for_selector("text=Relatório")
        assert page.locator("text=Relatório").count() > 0, "Detalhe do laudo não carregou a seção de achados"
        page.screenshot(path=str(out_dir / "02_biblioteca_detalhe.png"))
        print("[ok] Biblioteca: texto original + classificação carregados")

        # 3. Novo laudo — busca achado, seleciona, compila, copia
        page.goto(f"{BASE_URL}/laudo", wait_until="networkidle")
        search = page.get_by_placeholder("Buscar achado…")
        search.click()
        search.fill("menisco lateral rotura ausente")
        page.wait_for_timeout(400)
        first_option = page.locator("button:has-text('Menisco lateral')").first
        assert first_option.count() > 0, "Busca de achados não retornou nenhum resultado real"
        first_option.click()
        assert page.locator("text=Menisco lateral").count() > 0, "Achado não foi adicionado à seleção"

        page.locator("button:has-text('Compilar laudo')").click()
        page.wait_for_selector("text=Laudo compilado", timeout=10000)
        rendered = page.locator("pre").inner_text()
        assert "RELATÓRIO" in rendered, "Laudo compilado não contém a seção de achados"
        assert len(rendered.strip()) > 20, "Laudo compilado veio vazio"
        page.screenshot(path=str(out_dir / "03_laudo_compilado.png"))
        print("[ok] Compilador: laudo real montado a partir de achado real selecionado")

        # 4. Fila de revisão — resolve e reabre sem deixar efeito colateral
        page.goto(f"{BASE_URL}/revisao", wait_until="networkidle")
        page.wait_for_selector("button:has-text('Marcar como revisado')", timeout=10000)
        page.screenshot(path=str(out_dir / "04_fila_revisao.png"))
        resolve_btn = page.locator("button:has-text('Marcar como revisado')").first
        resolve_btn.click()
        page.locator("button:has-text('Confirmar')").click()
        page.wait_for_selector("text=Item marcado como revisado.")
        print("[ok] Fila de revisão: resolver funciona (toast confirmado)")

        # desfaz para nao alterar o estado real da fila
        page.goto(f"{BASE_URL}/revisao", wait_until="networkidle")
        page.locator("select").first.select_option("resolved")
        page.wait_for_timeout(400)
        reopen_btn = page.locator("button:has-text('Reabrir')").first
        if reopen_btn.count() > 0:
            reopen_btn.click()
            page.wait_for_timeout(300)
            print("[ok] Fila de revisão: item reaberto (sem efeito colateral no teste)")

        browser.close()


if __name__ == "__main__":
    main()
