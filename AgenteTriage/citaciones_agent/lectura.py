"""Lectura y extracción de señales del documento de la citación.

Respalda a la herramienta ``read``. DESCRIBE el documento; no lo interpreta.
La distinción es deliberada y aparece en varios sitios: si el documento dice
"10 días" sin calificar, ``unidad`` queda en ``None`` — decidir si un plazo es
hábil o calendario es asunto de la norma, y solo el corpus afirma unidades.

Ninguna función de este módulo lanza excepciones. Una herramienta que revienta
mata el turno del agente; una que devuelve ``{"ok": false, ...}`` le permite
recuperarse y seguir con la información que sí tiene.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from citaciones_agent.corpus import INDICE_SENALES_PROCESO
from citaciones_agent.texto import MESES, NUMERALES_ESCRITOS, normalizar, plegar

# Límites defensivos: el agente puede pasar cualquier cosa como "entrada".
LARGO_MAXIMO_RUTA = 400
TAMANO_MAXIMO_ARCHIVO = 200 * 1024      # 200 KB
LARGO_EXTRACTO = 400
MAXIMO_FECHAS = 8
MAXIMO_PLAZOS = 8
SUFIJOS_SOPORTADOS = {".txt", ".md"}

# Ciudades para decidir si el citado está en la misma ciudad del despacho.
# LISTA PARCIAL a propósito: cubre las capitales y ciudades principales, no los
# 1.100 municipios. Cuando no alcanza, el resultado es None (desconocido), nunca
# un False fabricado — asumir "otra ciudad" alargaría el plazo indebidamente.
CIUDADES = (
    "bogota", "medellin", "cali", "barranquilla", "cartagena", "cucuta",
    "bucaramanga", "pereira", "santa marta", "ibague", "manizales", "villavicencio",
    "pasto", "monteria", "neiva", "armenia", "popayan", "sincelejo", "valledupar",
    "tunja", "riohacha", "florencia", "quibdo", "yopal", "mocoa", "arauca",
    "leticia", "san andres", "soacha", "bello", "envigado", "itagui", "palmira",
    "buenaventura", "soledad", "girardot", "duitama", "sogamoso", "zipaquira",
    "facatativa", "fusagasuga", "chia", "barrancabermeja", "tulua", "cartago",
)

_RE_FECHA_LARGA = re.compile(
    r"\b(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})\b"
)
_RE_FECHA_BARRAS = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")
_RE_FECHA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# "diez (10) días hábiles", "10 días", "quince (15) dias calendario".
_RE_PLAZO = re.compile(
    r"(?:(?P<escrito>[a-z]+)\s+)?"
    r"\(?\s*(?P<num>\d{1,3})\s*\)?"
    r"\s+d[i]as?"
    r"(?:\s+(?P<unidad>habiles|calendario|corrientes|comunes))?"
)
# Plazo escrito solo con letras: "dentro de los tres dias siguientes".
_RE_PLAZO_ESCRITO = re.compile(
    r"\b(?P<escrito>[a-z]+)\s+d[i]as?"
    r"(?:\s+(?P<unidad>habiles|calendario|corrientes|comunes))?"
)

_RE_NORMA_NUMERADA = re.compile(
    r"\b(ley|decreto|resolucion|acuerdo|circular)\s+(\d{1,5})\s+de\s+(\d{4})\b"
)
_RE_ARTICULO = re.compile(r"\bart(?:iculo|\.)?\s*(\d{1,4})\b")

# Acrónimos y nombres de códigos, tal como se citan en la práctica.
_ACRONIMOS = {
    "cgp": "CGP (Código General del Proceso)",
    "codigo general del proceso": "Código General del Proceso",
    "cpaca": "CPACA (Ley 1437 de 2011)",
    "codigo de procedimiento administrativo": "CPACA",
    "estatuto tributario": "Estatuto Tributario",
    "e.t.": "Estatuto Tributario",
    "codigo nacional de policia": "Código Nacional de Policía (Ley 1801 de 2016)",
    "codigo nacional de seguridad y convivencia": "Ley 1801 de 2016",
    "codigo sustantivo del trabajo": "Código Sustantivo del Trabajo",
}

# Membrete: patrones de autoridad emisora, probados sobre el encabezado.
_RE_ENTIDADES = tuple(
    re.compile(p)
    for p in (
        r"juzgado[a-z0-9\s\.\-]{0,60}",
        r"tribunal[a-z0-9\s\.\-]{0,60}",
        r"direccion de impuestos[a-z\s]{0,40}",
        r"\bdian\b",
        r"ministerio de[l]? [a-z]{4,20}",
        r"inspeccion de policia[a-z0-9\s\.\-]{0,40}",
        r"inspeccion [a-z0-9\s]{0,20}de policia",
        r"centro de conciliacion[a-z\s\.\-]{0,40}",
        r"superintendencia de[l]? [a-z\s]{0,30}",
        r"superintendencia [a-z]{4,20}",
        r"alcaldia[a-z\s\.\-]{0,40}",
        r"gobernacion de[l]? [a-z\s]{0,25}",
        r"secretaria de [a-z\s]{0,30}",
        r"notaria [a-z0-9\s]{0,25}",
        r"fiscalia [a-z0-9\s]{0,30}",
        r"contraloria [a-z\s]{0,30}",
        r"procuraduria [a-z\s]{0,30}",
    )
)

_PALABRAS_EXTERIOR = ("en el exterior", "en el extranjero", "consulado", "consular")

# Marcadores del domicilio DEL CITADO. Son deliberadamente específicos: un
# "direccion" a secas empareja con "DIRECCIÓN DE IMPUESTOS Y ADUANAS" del
# membrete y hace creer que el citado vive en la ciudad de la entidad. Ese falso
# positivo fabrica un `misma_ciudad = True` y puede recortar el plazo de 10 a 5
# días, que es justo el error que este módulo tiene prohibido cometer.
_RE_MARCADORES_DOMICILIO = tuple(
    re.compile(p)
    for p in (
        r"direcci[o]n\s*(?:de\s+notificaci[o]n\w*)?\s*:",
        r"domicilio\s*:",
        r"domiciliad[oa]\s+en\b",
        r"residente\s+en\b",
        r"reside\s+en\b",
        r"ubicad[oa]\s+en\b",
        r"para\s+notificaciones\s*:?",
        r"recibir[a]?\s+notificaciones\s+en\b",
    )
)


def _parece_ruta(entrada: str) -> bool:
    """Reja estrecha: solo un string corto, de una línea y con sufijo conocido.

    Sin esta reja, cualquier citación de una sola línea intentaría abrirse como
    archivo. La herramienta no debe ganar capacidades de sistema de archivos
    por accidente.
    """
    if not entrada or len(entrada) > LARGO_MAXIMO_RUTA or "\n" in entrada:
        return False
    try:
        return Path(entrada).suffix.lower() in SUFIJOS_SOPORTADOS
    except (OSError, ValueError):
        return False


def _cargar(entrada: str) -> tuple[str, str, dict[str, Any] | None]:
    """Devuelve ``(texto, origen, error)``. ``error`` no None aborta la lectura."""
    if not _parece_ruta(entrada):
        # Caso normal: el agente pasó el texto de la citación directamente.
        if _tiene_sufijo_no_soportado(entrada):
            return "", "", {
                "ok": False,
                "error": "formato_no_soportado",
                "mensaje": (
                    "Solo se leen archivos .txt y .md. Convierta el documento a "
                    "texto plano o pegue su contenido directamente."
                ),
            }
        return entrada, "texto", None

    ruta = Path(entrada)
    try:
        if not ruta.is_file():
            return "", "", {
                "ok": False,
                "error": "archivo_no_encontrado",
                "mensaje": f"No existe el archivo: {entrada}",
            }
        if ruta.stat().st_size > TAMANO_MAXIMO_ARCHIVO:
            return "", "", {
                "ok": False,
                "error": "archivo_demasiado_grande",
                "mensaje": f"El archivo supera {TAMANO_MAXIMO_ARCHIVO // 1024} KB.",
            }
        return ruta.read_text(encoding="utf-8", errors="replace"), f"archivo:{ruta.name}", None
    except (OSError, ValueError) as exc:
        return "", "", {
            "ok": False,
            "error": "no_se_pudo_leer",
            "mensaje": f"{type(exc).__name__}: {exc}",
        }


def _tiene_sufijo_no_soportado(entrada: str) -> bool:
    """¿Es un string corto de una línea que apunta a un PDF/DOCX/etc.?"""
    if not entrada or len(entrada) > LARGO_MAXIMO_RUTA or "\n" in entrada:
        return False
    try:
        sufijo = Path(entrada).suffix.lower()
    except (OSError, ValueError):
        return False
    return sufijo in {".pdf", ".docx", ".doc", ".rtf", ".odt", ".xlsx", ".html"}


def _extraer_fechas(plegado: str, crudo: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Fechas en los tres formatos usuales, con su equivalente ISO."""
    fechas: list[dict[str, Any]] = []
    advertencias: list[str] = []
    vistas: set[str] = set()

    def agregar(inicio: int, fin: int, iso: str | None) -> None:
        crudo_txt = crudo[inicio:fin].strip()
        if crudo_txt in vistas:
            return
        vistas.add(crudo_txt)
        fechas.append({"crudo": crudo_txt, "iso": iso})

    for m in _RE_FECHA_LARGA.finditer(plegado):
        dia, mes_txt, anio = m.group(1), m.group(2), m.group(3)
        mes = MESES.get(mes_txt)
        iso = f"{anio}-{mes:02d}-{int(dia):02d}" if mes else None
        agregar(m.start(), m.end(), iso)

    for m in _RE_FECHA_ISO.finditer(plegado):
        agregar(m.start(), m.end(), f"{m.group(1)}-{m.group(2)}-{m.group(3)}")

    for m in _RE_FECHA_BARRAS.finditer(plegado):
        primero, segundo, anio = int(m.group(1)), int(m.group(2)), m.group(3)
        # Convención colombiana: dd/mm/yyyy. Si el primero es <= 12 el formato es
        # ambiguo y se anota; nunca se reinterpreta como mm/dd en silencio.
        if primero > 12:
            iso = f"{anio}-{segundo:02d}-{primero:02d}"
        else:
            iso = f"{anio}-{segundo:02d}-{primero:02d}" if segundo <= 12 else None
            if segundo <= 12:
                advertencias.append(
                    f"La fecha '{m.group(0)}' es ambigua; se interpretó como "
                    f"dd/mm/aaaa (convención colombiana)."
                )
        agregar(m.start(), m.end(), iso)

    return fechas[:MAXIMO_FECHAS], advertencias


def _extraer_plazos(plegado: str, crudo: str) -> list[dict[str, Any]]:
    """Plazos mencionados EN EL DOCUMENTO, sin interpretar la unidad.

    ``unidad`` queda en ``None`` si el texto no la califica. Adivinarla sería
    interpretar la ley, y de eso se encarga el corpus, no el lector.
    """
    plazos: list[dict[str, Any]] = []
    vistos: set[tuple[int, str | None]] = set()

    def agregar(inicio: int, fin: int, dias: int, unidad: str | None) -> None:
        if not (0 < dias <= 999) or (dias, unidad) in vistos:
            return
        vistos.add((dias, unidad))
        plazos.append(
            {"crudo": crudo[inicio:fin].strip(), "dias": dias, "unidad": unidad}
        )

    for m in _RE_PLAZO.finditer(plegado):
        unidad = m.group("unidad")
        agregar(m.start(), m.end(), int(m.group("num")), unidad or None)

    for m in _RE_PLAZO_ESCRITO.finditer(plegado):
        numero = NUMERALES_ESCRITOS.get(m.group("escrito"))
        if numero is None:
            continue
        agregar(m.start(), m.end(), numero, m.group("unidad") or None)

    return plazos[:MAXIMO_PLAZOS]


def _extraer_normas(plegado: str, crudo: str) -> list[str]:
    referencias: list[str] = []
    vistas: set[str] = set()

    def agregar(valor: str) -> None:
        clave = valor.lower()
        if clave not in vistas:
            vistas.add(clave)
            referencias.append(valor)

    for m in _RE_NORMA_NUMERADA.finditer(plegado):
        agregar(crudo[m.start():m.end()].strip())
    for m in _RE_ARTICULO.finditer(plegado):
        agregar(f"art. {m.group(1)}")
    for acronimo, etiqueta in _ACRONIMOS.items():
        if acronimo in plegado:
            agregar(etiqueta)

    return referencias[:12]


def _extraer_entidad(plegado: str, crudo: str) -> str | None:
    """Heurística de membrete sobre el encabezado. Devuelve None si no acierta.

    Precisión modesta a propósito: se mira solo el encabezado, porque el cuerpo
    de una citación menciona muchas entidades que no la emitieron.
    """
    encabezado = plegado[:800]
    mejor: tuple[int, int] | None = None
    for patron in _RE_ENTIDADES:
        m = patron.search(encabezado)
        if m and (mejor is None or m.start() < mejor[0]):
            mejor = (m.start(), m.end())
    if mejor is None:
        return None
    # Se recorta en el primer salto de línea: el patrón puede desbordarse al
    # renglón siguiente, que suele ser otra cosa (ciudad, radicado).
    fragmento = crudo[mejor[0]:mejor[1]].split("\n")[0]
    return " ".join(fragmento.split()).strip(" .,-:") or None


def _extraer_senales_proceso(plegado: str) -> list[dict[str, str]]:
    """Frases del corpus que delatan una variante concreta.

    Recorre ``INDICE_SENALES_PROCESO``, que ya viene ordenado de frase más larga
    a más corta. Ese orden es load-bearing: probar "proceso verbal" antes que
    "proceso verbal sumario" duplicaría el plazo de 10 a 20 días.
    """
    señales: list[dict[str, str]] = []
    consumidas: set[str] = set()
    for frase, tipo_id, variante_id in INDICE_SENALES_PROCESO:
        if len(frase) < 6 or frase in consumidas:
            continue
        if frase in plegado:
            # Si una frase más larga ya emparejó, sus subcadenas no aportan.
            if any(frase in previa for previa in consumidas):
                continue
            consumidas.add(frase)
            señales.append(
                {"frase": frase, "tipo_id": tipo_id, "variante_id": variante_id}
            )
    return señales[:6]


def _ciudades_en(fragmento: str) -> list[str]:
    return [c for c in CIUDADES if c in fragmento]


def _extraer_ubicacion(plegado: str) -> dict[str, Any]:
    """Señales de dónde está el citado. ``misma_ciudad`` es TRI-ESTADO.

    ``None`` significa "no se pudo determinar", y es el valor por defecto. Nunca
    se fabrica un ``False``: comparar municipios bien exigiría un listado
    completo, y un False erróneo alargaría el plazo de 5 a 10 días.
    """
    exterior = any(p in plegado for p in _PALABRAS_EXTERIOR)

    # Ciudad del despacho: la que aparece junto al membrete.
    ciudad_despacho = None
    encabezado = plegado[:800]
    candidatas_despacho = _ciudades_en(encabezado)
    if candidatas_despacho:
        ciudad_despacho = candidatas_despacho[0]

    # Ciudad del citado: la que aparece tras un marcador de domicilio.
    ciudad_citado = None
    for patron in _RE_MARCADORES_DOMICILIO:
        m = patron.search(plegado)
        if m is None:
            continue
        ventana = plegado[m.end():m.end() + 150]
        candidatas = _ciudades_en(ventana)
        if candidatas:
            ciudad_citado = candidatas[0]
            break

    misma_ciudad: bool | None = None
    if exterior:
        misma_ciudad = False
    elif ciudad_despacho and ciudad_citado:
        misma_ciudad = ciudad_despacho == ciudad_citado

    return {
        "exterior": exterior,
        "misma_ciudad": misma_ciudad,
        "ciudad_del_despacho": ciudad_despacho,
        "ciudad_del_citado": ciudad_citado,
    }


def leer_citacion(entrada: str) -> dict[str, Any]:
    """Lee la citación y extrae las señales que el agente necesita.

    ``entrada`` es el texto de la citación o, si es un string corto de una línea
    terminado en ``.txt``/``.md`` que existe en disco, la ruta a ese archivo.
    """
    if not isinstance(entrada, str) or not entrada.strip():
        return {
            "ok": False,
            "error": "entrada_vacia",
            "mensaje": "Pase el texto de la citación o la ruta a un archivo .txt.",
        }

    texto, origen, error = _cargar(entrada)
    if error is not None:
        return error
    if not texto.strip():
        return {
            "ok": False,
            "error": "documento_vacio",
            "mensaje": f"El origen '{origen}' no contiene texto.",
        }

    plegado = plegar(texto)          # mismos offsets que ``texto``
    normalizado = normalizar(texto)  # espacios colapsados, para frases

    fechas, advertencias = _extraer_fechas(plegado, texto)
    plazos = _extraer_plazos(plegado, texto)
    entidad = _extraer_entidad(plegado, texto)
    ubicacion = _extraer_ubicacion(normalizado)

    if entidad is None:
        advertencias.append(
            "No se pudo identificar la entidad emisora en el encabezado."
        )
    if ubicacion["misma_ciudad"] is None and not ubicacion["exterior"]:
        advertencias.append(
            "No se pudo determinar si el citado está en la ciudad del despacho; "
            "si el tipo de citación lo requiere, asuma la hipótesis más corta."
        )
    if any(p["unidad"] is None for p in plazos):
        advertencias.append(
            "Algún plazo del documento no indica si son días hábiles o "
            "calendario: la unidad la fija la norma, no el documento."
        )

    extracto = " ".join(texto[:LARGO_EXTRACTO].split())

    return {
        "ok": True,
        "origen": origen,
        "longitud_original": len(texto),
        # Sin el texto completo a propósito: el agente ya lo tiene en su prompt
        # y devolverlo otra vez solo duplicaría contexto.
        "extracto": extracto,
        "fechas": fechas,
        "plazos_mencionados": plazos,
        "entidad_emisora": entidad,
        "referencias_normativas": _extraer_normas(plegado, texto),
        "senales_tipo_proceso": _extraer_senales_proceso(normalizado),
        "senales_ubicacion": ubicacion,
        "advertencias": advertencias,
    }
