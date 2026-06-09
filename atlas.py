# Atlas de maturação esquelética baseado em Greulich & Pyle
# Organizado por faixa etária em meses

ATLAS = {
    (0, 12): {
        "titulo": "0 – 12 meses",
        "carpo": [
            "Ossos do carpo não ossificados ou com núcleos de ossificação iniciais.",
            "Capitato e hamato podem apresentar núcleos de ossificação primários.",
        ],
        "epifises": [
            "Epífises distais do rádio e ulna ausentes ou com núcleos puntiformes.",
            "Epífises das falanges e metacarpos ainda não visíveis.",
        ],
        "referencia_gp": "G&P: padrão neonatal a 1 ano"
    },
    (12, 24): {
        "titulo": "1 – 2 anos",
        "carpo": [
            "Capitato e hamato ossificados.",
            "Piramidal pode iniciar ossificação ao redor dos 18 meses.",
        ],
        "epifises": [
            "Epífise distal do rádio visível como disco achatado.",
            "Epífises das falanges proximais visíveis.",
            "Epífises dos metacarpos II–V começam a aparecer.",
        ],
        "referencia_gp": "G&P: padrão 1–2 anos"
    },
    (24, 36): {
        "titulo": "2 – 3 anos",
        "carpo": [
            "Piramidal ossificado.",
            "Semilunar pode iniciar ossificação.",
            "Grande e hamato bem definidos.",
        ],
        "epifises": [
            "Epífise distal do rádio com forma oval definida.",
            "Epífises das falanges médias e distais visíveis.",
            "Epífise do primeiro metacarpo visível.",
        ],
        "referencia_gp": "G&P: padrão 2–3 anos"
    },
    (36, 54): {
        "titulo": "3 – 4,5 anos",
        "carpo": [
            "Semilunar ossificado.",
            "Escafóide inicia ossificação.",
            "Trapézio e trapezoide podem aparecer.",
        ],
        "epifises": [
            "Epífise distal do rádio mais larga, ainda sem fusão.",
            "Epífises das falanges bem definidas.",
            "Epífise distal da ulna pode iniciar ossificação.",
        ],
        "referencia_gp": "G&P: padrão 3–4 anos"
    },
    (54, 72): {
        "titulo": "4,5 – 6 anos",
        "carpo": [
            "Escafóide ossificado.",
            "Trapézio e trapezoide visíveis.",
            "Todos os ossos do carpo presentes exceto pisiforme.",
        ],
        "epifises": [
            "Epífise distal do rádio: forma retangular, bordas nítidas.",
            "Epífise distal da ulna visível como disco.",
            "Epífises das falanges com aspecto regular e simétrico.",
        ],
        "referencia_gp": "G&P: padrão 5–6 anos"
    },
    (72, 96): {
        "titulo": "6 – 8 anos",
        "carpo": [
            "Todos os ossos do carpo ossificados exceto pisiforme.",
            "Escafóide, semilunar e piramidal com contornos bem definidos.",
            "Pisiforme pode iniciar ossificação ao redor dos 8 anos (feminino mais precoce).",
        ],
        "epifises": [
            "Epífise distal do rádio: largura próxima à metáfise.",
            "Epífise distal da ulna em forma de cúpula.",
            "Epífises das falanges proximais com aspecto quadrangular.",
            "Sesamoide do polegar pode aparecer ao final desta faixa.",
        ],
        "referencia_gp": "G&P: padrão 6–8 anos"
    },
    (96, 120): {
        "titulo": "8 – 10 anos",
        "carpo": [
            "Pisiforme ossificado (feminino ~8 anos; masculino ~10 anos).",
            "Carpo com morfologia adulta em desenvolvimento.",
        ],
        "epifises": [
            "Epífise distal do rádio: igual ou maior que a largura da metáfise.",
            "Epífise distal da ulna com bordas nítidas e forma estável.",
            "Sesamoide do polegar presente.",
            "Epífises das falanges com aspecto robusto.",
        ],
        "referencia_gp": "G&P: padrão 8–10 anos"
    },
    (120, 144): {
        "titulo": "10 – 12 anos",
        "carpo": [
            "Carpo totalmente ossificado.",
            "Pisiforme com forma definitiva.",
            "Articulações do carpo com espaços bem definidos.",
        ],
        "epifises": [
            "Epífise distal do rádio: ultrapassa a largura da metáfise.",
            "Epífise distal da ulna com estilóide ulnar visível.",
            "Epífises das falanges com início de achatamento (cap-stage).",
            "Feminino: sinais iniciais de fusão epifisária nas falanges distais.",
        ],
        "referencia_gp": "G&P: padrão 10–12 anos"
    },
    (144, 168): {
        "titulo": "12 – 14 anos",
        "carpo": [
            "Carpo com aspecto adulto.",
            "Ossos do carpo com tamanho definitivo.",
        ],
        "epifises": [
            "Feminino: fusão epifisária iniciando nas falanges distais e médias.",
            "Masculino: epífises ainda abertas, sem fusão significativa.",
            "Epífise distal do rádio: início de fusão no feminino (~13 anos).",
            "Epífise da ulna: estilóide bem definido.",
        ],
        "referencia_gp": "G&P: padrão 12–14 anos"
    },
    (168, 192): {
        "titulo": "14 – 16 anos",
        "carpo": [
            "Carpo com aspecto adulto completo.",
        ],
        "epifises": [
            "Feminino: fusão completa das falanges distais e médias; rádio em fusão.",
            "Masculino: fusão iniciando nas falanges distais; rádio ainda aberto.",
            "Epífise distal do rádio: fusão parcial a completa no feminino.",
            "Placa de crescimento do rádio: fechamento iminente no feminino.",
        ],
        "referencia_gp": "G&P: padrão 14–16 anos"
    },
    (192, 216): {
        "titulo": "16 – 18 anos",
        "carpo": [
            "Carpo adulto.",
        ],
        "epifises": [
            "Feminino: fusão completa em rádio e ulna; esqueleto maduro.",
            "Masculino: fusão completa das falanges; rádio em fusão final.",
            "Placa de crescimento do rádio: fechada no feminino; fechando no masculino.",
        ],
        "referencia_gp": "G&P: padrão 16–18 anos"
    },
    (216, 999): {
        "titulo": "≥ 18 anos",
        "carpo": [
            "Carpo totalmente ossificado e com aspecto adulto.",
        ],
        "epifises": [
            "Fusão epifisária completa em todos os segmentos.",
            "Rádio e ulna: fusão completa, sem placa de crescimento visível.",
            "Esqueleto maduro — estimativa de idade óssea não aplicável por este método.",
        ],
        "referencia_gp": "G&P: esqueleto adulto"
    },
}

def get_atlas(idade_meses: float) -> dict:
    for (inicio, fim), dados in ATLAS.items():
        if inicio <= idade_meses < fim:
            return dados
    return ATLAS[(216, 999)]
