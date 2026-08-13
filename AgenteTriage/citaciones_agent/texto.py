"""Utilidades de texto en español. Stdlib puro, sin dependencias.

Es la base de ``busqueda`` (emparejamiento contra el corpus) y de ``lectura``
(extracción de señales del documento). No importa nada del paquete.
"""

from __future__ import annotations

import re
import unicodedata

# Stopwords generales del español. No incluye vocabulario jurídico: ese lo
# calcula ``corpus`` solo, mirando qué tokens aparecen en casi todos los tipos.
STOPWORDS_ES: frozenset[str] = frozenset(
    """
    a al algo alguna algunas alguno algunos ante antes aquel aquella aquellas
    aquellos aqui como con contra cual cuales cuando de del desde donde dos e el
    ella ellas ello ellos en entre era eran es esa esas ese eso esos esta estan
    estas este esto estos fue fueron ha han hasta hay la las le les lo los mas me
    mi mis mucho muy no nos o os otra otras otro otros para pero poco por porque
    que quien quienes se sea sean segun ser si sido sin sobre solo son su sus
    tambien tanto te tiene tienen todo todos tras un una uno unos y ya
    """.split()
)

# Meses en español ya normalizados (sin tildes), para parsear "12 de marzo de 2026".
MESES: dict[str, int] = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Numerales escritos que aparecen en plazos legales. Cubre de sobra el corpus;
# no pretende ser un parser general de números en español.
NUMERALES_ESCRITOS: dict[str, int] = {
    "un": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veinticinco": 25,
    "treinta": 30, "cuarenta": 40, "cuarenta y cinco": 45, "sesenta": 60,
    "noventa": 90,
}

_NO_ALFANUMERICO = re.compile(r"[^a-z0-9]+")
_ESPACIOS = re.compile(r"\s+")


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios colapsados.

    Descompone en NFD y descarta los diacríticos, así "notificación" y
    "notificacion" emparejan. La ``ñ`` cae a ``n`` como efecto secundario, lo
    cual AYUDA al emparejamiento (nadie escribe "amojonamiento" mal por la eñe,
    pero sí hay documentos escaneados que pierden la tilde).
    """
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    sin_tildes = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return _ESPACIOS.sub(" ", sin_tildes).strip()


def plegar(texto: str) -> str:
    """Minúsculas sin tildes CONSERVANDO la longitud y los offsets del original.

    ``normalizar()`` colapsa espacios y por tanto desplaza los offsets, lo que
    impide recuperar el fragmento original a partir del span de una coincidencia.
    ``plegar()`` mapea carácter a carácter, así que ``plegar(t)[i]`` corresponde
    siempre a ``t[i]`` y ``lectura`` puede emparejar sin tildes pero devolver el
    texto tal como venía, con sus mayúsculas y sus acentos.
    """
    salida = []
    for caracter in texto.lower():
        descompuesto = unicodedata.normalize("NFD", caracter)
        base = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
        salida.append(base[0] if base else caracter)
    return "".join(salida)


def tokenizar(texto: str, *, stopwords: frozenset[str] = STOPWORDS_ES) -> set[str]:
    """Conjunto de tokens normalizados, sin stopwords ni tokens de 1-2 letras.

    Devuelve un ``set`` y no una lista a propósito: el scoring de ``busqueda``
    usa intersecciones, y contar repeticiones premiaría a los documentos largos.
    """
    crudo = _NO_ALFANUMERICO.sub(" ", normalizar(texto))
    return {
        token
        for token in crudo.split()
        if len(token) > 2 and token not in stopwords
    }


def contiene_frase(texto_normalizado: str, frase: str) -> bool:
    """¿La frase (ya normalizada) aparece en el texto (ya normalizado)?

    Ambos argumentos vienen de ``normalizar()``, así que basta ``in``. Se separa
    en función propia porque es el predicado con más peso del scoring y conviene
    poder cambiarlo en un solo sitio.
    """
    return frase in texto_normalizado
