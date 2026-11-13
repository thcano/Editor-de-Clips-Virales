"""Léxicos en español y utilidades de normalización de texto."""

from __future__ import annotations

import re
import unicodedata

WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9%]+")
NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*%?\b")

STOPWORDS = frozenset(
    """
    a al algo algunas algunos ante antes aquel aquella aquellas aquellos aqui asi aun aunque
    bajo bien cada casi como con contra cual cuales cuando de del desde donde dos durante e el
    ella ellas ellos en entre era erais eran eras eres es esa esas ese eso esos esta estaba
    estaban estado estamos estan estar estas este esto estos estoy fue fueron fui ha habia
    habian han has hasta hay la las le les lo los mas me mi mis mucho muchos muy nada ni no nos
    nosotros nuestra nuestras nuestro nuestros o os otra otras otro otros para pero poco por
    porque que quien quienes se sea sean segun ser si sido siempre sin sobre sois somos son soy
    su sus tambien tan tanto te tiene tienen tienes todo todos tu tus un una uno unos vosotras
    vosotros vuestra vuestras vuestro vuestros y ya yo
    """.split()
)

CURIOSITY_WORDS = frozenset(
    """
    nadie nunca jamas siempre secreto secretos error errores verdad mentira clave truco trucos
    consejo consejos atencion mira escucha imagina increible impresionante brutal polemico
    polemica controvertido controvertida prohibido oculto oculta revelacion revelaciones
    gratis facil rapido cambia cambio descubri descubrimiento olvida olvidar deja dejar empieza
    empezar importante esencial unico
    """.split()
)
CURIOSITY_PHRASES = (
    "por que",
    "esto es",
    "lo que nadie",
    "te cuento",
    "te cuenta",
    "no te",
    "de verdad",
    "en realidad",
    "resulta que",
    "te voy a contar",
    "no vas a creer",
)

EMOTION_WORDS = frozenset(
    """
    increible brutal terrible horrible impresionante enorme bestial locura amor odio miedo
    rabia felicidad dolor triste feliz enojado enfadado sorprendente impactante conmovedor
    emocionante vergonzoso ridiculo perfecto desastroso maravilloso espantoso aterrador
    decepcionante ilusionante
    """.split()
)

STORY_WORDS = frozenset(
    """
    cuando entonces resulta historia recuerdo aprendi descubri decidi empezo termino despues
    luego finalmente recuerda
    """.split()
)
STORY_PHRASES = (
    "de repente",
    "un dia",
    "me paso",
    "nos paso",
    "erase una vez",
    "habia una vez",
    "al final",
    "resulta que",
)

ADVICE_WORDS = frozenset(
    """
    debes debe deberias tienes hay truco secreto clave paso pasos primero segundo tercero tip
    tips consejo consejos aprende haz evita prueba usa utiliza recuerda mejor peor
    """.split()
)
ADVICE_PHRASES = (
    "tienes que",
    "hay que",
    "el truco",
    "el secreto",
    "la clave",
    "deja de",
    "empieza a",
    "no hagas",
    "nunca hagas",
    "lo que tienes que",
)

CONTROVERSY_WORDS = frozenset(
    """
    polemico polemica controvertido controvertida mentira verdad odio peor mejor absurdo
    ridiculo equivocas equivocados sinceramente honestamente
    """.split()
)
CONTROVERSY_PHRASES = (
    "no estoy de acuerdo",
    "en mi opinion",
    "yo creo",
    "la verdad es",
    "te equivocas",
    "estan equivocados",
)

FILLER_WORDS = frozenset(
    """
    eh em mmm bueno pues tipo obviamente basicamente digamos rollo cosa cosas
    """.split()
)
FILLER_PHRASES = ("o sea", "como que", "en plan", "algo asi", "valga la redundancia")

NUMBER_WORDS = frozenset("cien mil millon millones porcentaje".split())
NUMBER_PHRASES = ("por ciento",)

INTERROGATIVES = frozenset(
    "que como cuando donde quien cual cuanto cuanta cuantos cuantas".split()
)

CORPORATE_WORDS = frozenset(
    """
    sinergia sinergias optimizar optimizacion kpi kpis roi stakeholder stakeholders leverage
    escalar escalabilidad monetizar monetizacion branding engagement funnel pipeline roadmap
    deliverable deliverables corporativo corporativa
    """.split()
)
CORPORATE_PHRASES = (
    "value proposition",
    "best practices",
    "estrategia empresarial",
    "propuesta de valor",
)


def normalize_text(text: str) -> str:
    """Minúsculas sin acentos, para comparar marcadores."""

    lowered = text.lower()
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def tokenize(text: str) -> list[str]:
    """Tokeniza preservando acentos y signos de porcentaje."""

    return WORD_RE.findall(text)


def normalize_token(token: str) -> str:
    return normalize_text(token)


def is_corporate(text: str) -> bool:
    """Detecta lenguaje corporativo que rompe el tono conversacional."""

    normalized = normalize_text(text)
    tokens = {normalize_token(token) for token in tokenize(text)}
    if tokens & CORPORATE_WORDS:
        return True
    return any(phrase in normalized for phrase in CORPORATE_PHRASES)
