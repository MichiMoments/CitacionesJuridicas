"""Búsqueda de referencias normativas sobre el corpus local.

Respalda a la herramienta ``search`` del agente. Stdlib puro, sin red y sin
dependencias: el mismo texto siempre produce el mismo resultado, lo cual
importa cuando lo que está en juego es un término perentorio.

El respaldo web NO está implementado (decisión del dueño del proyecto). La
costura está lista y documentada en ``_respaldo_web``; hoy devuelve un marcador
estructurado ``sin_backend`` y el agente sigue trabajando con el corpus local.
"""

from __future__ import annotations

import re
from typing import Any

from citaciones_agent.corpus import (
    CORPUS_CITACIONES,
    STOPWORDS_DEL_DOMINIO,
    TipoCitacion,
)
from citaciones_agent.texto import STOPWORDS_ES, contiene_frase, normalizar, tokenizar

# Pesos del scoring. Las frases valen el triple porque son lo único realmente
# diagnóstico: "citacion" aparece en casi todo el corpus, pero "inspeccion de
# policia" o "requerimiento ordinario de informacion" identifican un tipo solas.
PESO_FRASE = 3.0
PESO_TOKEN_CURADO = 2.0
PESO_TOKEN_GENERAL = 1.0

# Constante de saturación de la normalización x/(x+K).
K_SATURACION = 6.0

# Umbrales de decisión. SIN CALIBRAR: se eligieron a ojo y hay que ajustarlos
# con 10-20 citaciones reales. El demo imprime los puntajes justamente para eso.
UMBRAL_FUERTE = 0.55
UMBRAL_DEBIL = 0.30
BRECHA_MINIMA = 0.10

_STOPWORDS_COMPLETAS = STOPWORDS_ES | STOPWORDS_DEL_DOMINIO

# Canoniza las citas de artículos para que "artículo 261", "art. 261" y "art 261"
# emparejen entre sí. Se aplica por igual a la consulta y a las normas del corpus.
_RE_ARTICULO = re.compile(r"\bart(?:iculo|\.)?\s*(\d{1,4})\b")


def _canonizar(texto_normalizado: str) -> str:
    return _RE_ARTICULO.sub(r"art \1", texto_normalizado)


def _perfil(tipo: TipoCitacion) -> tuple[tuple[str, ...], set[str], set[str]]:
    """Precalcula frases, tokens curados y tokens generales de un tipo.

    Las NORMAS entran como FRASES, nunca como tokens. Tokenizarlas fue un error
    real y caro: "ley 2220 de 2022" se partía en {"ley", "2220", "2022"}, con lo
    cual el token "ley" quedaba como palabra curada (peso alto) de casi todos los
    tipos y CUALQUIER documento que citara cualquier norma emparejaba. Peor aún,
    los años sueltos emparejaban entre normas distintas: una citación que
    mencionaba la "Ley 675 de 2001" puntuaba contra la "Ley 640 de 2001" solo por
    compartir el año. Como frase, en cambio, "ley 1801 de 2016" es de las señales
    más diagnósticas que existen.
    """
    frases = tuple(
        _canonizar(normalizar(f)) for f in (*tipo.frases_clave, *tipo.normas)
    )

    curados = set(tipo.palabras_clave)

    # `nota` queda FUERA a propósito: es metadato de procedencia para humanos
    # ("el dato de origen no califica la unidad; se asume hábiles"), no una
    # descripción del tipo. Incluirla metía en el índice palabras como "unidad",
    # "dato" u "origen", que emparejaban con documentos por pura coincidencia
    # léxica — un documento sobre una "unidad privada 302" puntuaba contra tres
    # tipos del corpus.
    texto_general = " ".join(
        [tipo.nombre, tipo.descripcion]
        + [f"{v.acto} {v.condicion}" for v in tipo.variantes]
    )
    generales = tokenizar(texto_general, stopwords=_STOPWORDS_COMPLETAS) - curados

    return frases, curados, generales


# Se calcula una sola vez al importar: el corpus es inmutable.
_PERFILES: dict[str, tuple[tuple[str, ...], set[str], set[str]]] = {
    tipo_id: _perfil(tipo) for tipo_id, tipo in CORPUS_CITACIONES.items()
}


def puntuar(consulta: str, tipo_id: str) -> tuple[float, list[str]]:
    """Puntaje en (0,1) de un tipo frente a la consulta, más las señales usadas.

    La normalización es saturante ``x/(x+K)`` y no una división por el máximo
    posible de cada tipo. Dividir por el máximo penalizaría a los tipos con
    descripción larga (denominador grande) — un sesgo puramente accidental que
    no tiene nada que ver con qué tan bien empareja el documento.
    """
    frases, curados, generales = _PERFILES[tipo_id]

    consulta_norm = _canonizar(normalizar(consulta))
    tokens_consulta = tokenizar(consulta, stopwords=_STOPWORDS_COMPLETAS)

    frases_ok = [f for f in frases if contiene_frase(consulta_norm, f)]
    curados_ok = sorted(curados & tokens_consulta)
    generales_ok = sorted(generales & tokens_consulta)

    crudo = (
        PESO_FRASE * len(frases_ok)
        + PESO_TOKEN_CURADO * len(curados_ok)
        + PESO_TOKEN_GENERAL * len(generales_ok)
    )
    puntaje = crudo / (crudo + K_SATURACION) if crudo else 0.0

    señales = [f"frase:{f}" for f in frases_ok] + curados_ok + generales_ok
    return puntaje, señales


def buscar_local(consulta: str, max_resultados: int = 3) -> list[dict[str, Any]]:
    """Tipos del corpus ordenados por puntaje descendente (solo los > 0)."""
    puntuados = []
    for tipo_id, tipo in CORPUS_CITACIONES.items():
        puntaje, señales = puntuar(consulta, tipo_id)
        if puntaje <= 0.0:
            continue
        puntuados.append(
            {
                "tipo_id": tipo_id,
                "nombre": tipo.nombre,
                "fundamento": tipo.fundamento,
                "puntaje": round(puntaje, 3),
                "senales": señales[:8],
                "plazos_del_citado": [
                    {
                        "variante_id": v.id,
                        "acto": v.acto,
                        "condicion": v.condicion,
                        "dias_habiles": v.dias_habiles,
                        "unidad_original": v.unidad.value,
                    }
                    for v in tipo.variantes_del_citado()
                ],
            }
        )

    puntuados.sort(key=lambda r: r["puntaje"], reverse=True)
    return puntuados[: max(1, max_resultados)]


def clasificar_fuerza(resultados: list[dict[str, Any]]) -> str:
    """Qué tan confiable es la coincidencia: fuerte | media | debil | nula.

    "media" cubre el empate: si el primero y el segundo están a menos de
    ``BRECHA_MINIMA``, el corpus no está distinguiendo y conviene que el agente
    lo sepa en vez de quedarse con el primero por azar del orden.
    """
    if not resultados:
        return "nula"

    mejor = resultados[0]["puntaje"]
    if mejor < UMBRAL_DEBIL:
        return "debil"

    if len(resultados) > 1 and (mejor - resultados[1]["puntaje"]) < BRECHA_MINIMA:
        return "media"

    return "fuerte" if mejor >= UMBRAL_FUERTE else "media"


def _respaldo_web(consulta: str, max_resultados: int) -> dict[str, Any]:
    """Respaldo web: NO IMPLEMENTADO por decisión del dueño del proyecto.

    Devuelve un marcador estructurado en vez de lanzar, para que una coincidencia
    débil degrade a "sigue con el corpus local" y no mate el turno del agente.

    TODO (pendiente, diseño ya acordado):
      - Adaptadores por proveedor, cada uno con import DIFERIDO dentro de
        ``try/except ImportError`` y un ``except Exception`` amplio A PROPÓSITO:
        red caída, rate-limit y cambios de firma entre versiones tienen que
        volverse un marcador estructurado, nunca una excepción.
      - Orden sugerido: Tavily si existe ``TAVILY_API_KEY`` (pensado para
        agentes, snippets limpios, API estable), y ``ddgs`` como alternativa sin
        clave. Advertencia sobre ``ddgs``: es un scraper NO oficial, el paquete
        se renombró (antes ``duckduckgo-search``) y sus firmas cambian entre
        versiones menores — hay que pinnear la versión exacta y asumir que se
        romperá.
      - Todo resultado web debe viajar con la advertencia de "sin verificar":
        una fuente web no es fundamento normativo, y el prompt ya obliga a
        declararlo en el resumen si la respuesta se apoyó en ella.
      - Añadir la dependencia elegida a requirements.txt (hoy está comentada).
    """
    return {
        "estado": "sin_backend",
        "motivo": (
            "Respaldo web no implementado (pendiente). La búsqueda usó "
            "únicamente el corpus normativo local."
        ),
        "resultados": [],
    }


def buscar_referencias(consulta: str, max_resultados: int = 3) -> dict[str, Any]:
    """Busca el fundamento normativo que corresponde a una citación.

    Primero el corpus local. Si la coincidencia es débil o nula, consulta el
    respaldo web — que hoy está deshabilitado y responde ``sin_backend``.
    """
    consulta = (consulta or "").strip()
    if not consulta:
        return {
            "ok": False,
            "error": "consulta_vacia",
            "mensaje": "Pase el texto o las palabras clave de la citación.",
            "resultados": [],
            "fuerza": "nula",
        }

    resultados = buscar_local(consulta, max_resultados)
    fuerza = clasificar_fuerza(resultados)

    salida: dict[str, Any] = {
        "ok": True,
        "fuente": "corpus_local",
        "fuerza": fuerza,
        "umbrales": {"fuerte": UMBRAL_FUERTE, "debil": UMBRAL_DEBIL},
        "resultados": resultados,
    }

    if fuerza in ("debil", "nula"):
        salida["respaldo_web"] = _respaldo_web(consulta, max_resultados)
        salida["sugerencia"] = (
            "Ningún tipo del corpus empareja con claridad. Llame a "
            "time_determination igualmente: devolverá la ruta de razonamiento "
            "para citaciones fuera del corpus."
        )

    return salida
