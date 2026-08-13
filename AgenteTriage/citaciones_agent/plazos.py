"""Determinación del plazo de respuesta a partir del corpus.

Respalda a la herramienta ``time_determination``. Aquí ocurre TODA la
aritmética de días: el modelo nunca convierte ni suma nada, solo recibe el
número ya resuelto y lo justifica. Es la misma separación de EDCO entre la
regla pura (``whitelist.valida``) y el gate que la aplica (``pipeline_adapter``).

El "diccionario con los tipos y sus días" que pide el diseño ES el corpus: es
el RESPALDO de esta función, no un argumento. Pasarle el corpus al modelo para
que lo devuelva sería invitarlo a mutarlo — y además un parámetro de tipo dict
se degrada silenciosamente a string en el function-calling de Gemini.
"""

from __future__ import annotations

from typing import Any

from citaciones_agent.busqueda import (
    UMBRAL_DEBIL,
    UMBRAL_FUERTE,
    buscar_local,
    puntuar,
)
from citaciones_agent.corpus import (
    PLAZOS_DE_REFERENCIA,
    TipoCitacion,
    VarianteCitacion,
    calendario_a_habiles,
    tipo as tipo_del_corpus,
)
from citaciones_agent.schemas import NaturalezaPlazo

# Ruta de razonamiento para citaciones que no están en el corpus. No incluye
# ningún número inventado: las anclas salen de PLAZOS_DE_REFERENCIA, que se
# deriva del propio corpus.
GUIA_RAZONAMIENTO: tuple[str, ...] = (
    "Identifique la autoridad emisora y la naturaleza del asunto: judicial, "
    "administrativo, tributario, policivo o laboral.",
    "Busque en el documento un plazo expreso. Si existe y está en días hábiles, "
    "ese es el plazo.",
    "Si el plazo expreso está en días calendario, conviértalo de forma "
    "conservadora (aproximadamente cinco séptimos, redondeando hacia abajo).",
    "Si no hay plazo expreso, razone por analogía con el tipo del corpus más "
    "cercano por autoridad y por materia.",
    "Entre varios plazos análogos plausibles, elija SIEMPRE el más corto.",
    "Declare en el resumen que no hubo coincidencia con el corpus y que el "
    "plazo es una estimación, no un término verificado contra la norma.",
)


def _variante_a_dict(variante: VarianteCitacion, tipo: TipoCitacion) -> dict[str, Any]:
    return {
        "variante_id": variante.id,
        "acto": variante.acto,
        "condicion": variante.condicion,
        "dias_segun_la_norma": variante.dias,
        "unidad_segun_la_norma": variante.unidad.value,
        "dias_habiles": variante.dias_habiles,
        "fundamento": tipo.fundamento_de(variante),
        "nota": variante.nota,
    }


_COLA_ADVERTENCIA_CALENDARIO = (
    "La conversión no descuenta festivos, así que cuente los días hábiles "
    "reales desde la notificación y responda con antelación."
)


def _texto_advertencia_calendario_norma(
    variante: VarianteCitacion, tipo: TipoCitacion
) -> str:
    """Frase literal en español que el resumen debe incluir tal cual.

    Se entrega redactada, y no como un booleano que el modelo deba interpretar,
    porque es lo más barato que garantiza que el caveat aparezca en la salida.
    """
    return (
        f"ATENCIÓN: {tipo.fundamento_de(variante)} fija este plazo en "
        f"{variante.dias} días CALENDARIO, no hábiles. Se convirtió de forma "
        f"conservadora a {variante.dias_habiles} días hábiles. "
        f"{_COLA_ADVERTENCIA_CALENDARIO}"
    )


def _texto_advertencia_calendario_documento(dias_documento: int, habiles: int) -> str:
    """Variante de la advertencia cuando el calendario lo trae el documento.

    No puede reusar la de la norma: esa cita los días del corpus, y aquí el
    número en calendario es el del oficio recibido.
    """
    return (
        f"ATENCIÓN: el documento expresa el plazo en {dias_documento} días "
        f"CALENDARIO, no hábiles. Se convirtió de forma conservadora a "
        f"{habiles} días hábiles. {_COLA_ADVERTENCIA_CALENDARIO}"
    )


def _dias_del_documento_a_habiles(dias: int, unidad: str | None) -> tuple[int, bool]:
    """Normaliza a hábiles el plazo que trae el propio documento.

    Devuelve ``(dias_habiles, era_calendario)``. Si el documento no califica la
    unidad se asume HÁBILES: es lo que dice la mayoría de los oficios, y asumir
    calendario recortaría el plazo sin fundamento.
    """
    if unidad and unidad.strip().lower().startswith("calend"):
        return calendario_a_habiles(dias), True
    return dias, False


def _resolver_sin_coincidencia(senales: str, confianza: float) -> dict[str, Any]:
    """Rama para citaciones fuera del corpus: guía, no un número inventado."""
    return {
        "estado": "sin_coincidencia",
        "tipo_id": None,
        "tipo_nombre": None,
        "fundamento": None,
        "dias_habiles_recomendados": None,
        "requiere_desambiguacion": False,
        "confianza_corpus": round(confianza, 3),
        "plazos_de_referencia_del_corpus": list(PLAZOS_DE_REFERENCIA),
        "guia_razonamiento": list(GUIA_RAZONAMIENTO),
        "advertencia_calendario": False,
        "texto_advertencia_calendario": "",
        "advertencias": [
            "La citación no coincide con ningún tipo del corpus. El plazo que "
            "usted determine es una ESTIMACIÓN y debe declararse como tal en el "
            "resumen.",
        ],
        "consulta_evaluada": senales[:200],
    }


def determinar_plazo(
    tipo_id: str | None = None,
    senales: str = "",
    variante_id: str | None = None,
    dias_indicados_en_documento: int | None = None,
    unidad_dias_indicados: str | None = None,
) -> dict[str, Any]:
    """Resuelve el plazo máximo de respuesta, en días hábiles.

    ``tipo_id`` viene normalmente de ``search``. Si falta o es inválido, se
    infiere del texto de ``senales`` reusando el mismo scorer — así el agente
    que se saltó ``search`` no queda bloqueado, y no hay una segunda
    implementación de emparejamiento que se pueda desincronizar.
    """
    tipo = tipo_del_corpus(tipo_id) if tipo_id else None
    confianza = 1.0 if tipo else 0.0
    corroboracion: list[str] = []

    # Un `tipo_id` recibido NO se toma como verdad. Si además llegan `senales`,
    # se contrasta el tipo contra ellas: sin esto, un tipo_id equivocado producía
    # una respuesta segura de sí misma citando una norma que no viene al caso —
    # que en materia legal es peor que no responder.
    if tipo is not None and senales.strip():
        confianza, _ = puntuar(senales, tipo.id)
        if confianza < UMBRAL_DEBIL:
            corroboracion.append(
                f"El tipo '{tipo.id}' NO se corrobora con el texto de la citación "
                f"(puntaje {confianza:.2f}). Se trata el caso como fuera del corpus."
            )
            salida_sin = _resolver_sin_coincidencia(senales, confianza)
            salida_sin["advertencias"] = corroboracion + salida_sin["advertencias"]
            salida_sin["tipo_id_descartado"] = tipo.id
            return salida_sin
        if confianza < UMBRAL_FUERTE:
            corroboracion.append(
                f"La coincidencia con '{tipo.id}' es apenas parcial (puntaje "
                f"{confianza:.2f}): verifique que el fundamento normativo "
                f"corresponda y dígalo en el resumen si hay duda."
            )

    if tipo is None:
        consulta = senales or tipo_id or ""
        candidatos_busqueda = buscar_local(consulta, 1) if consulta.strip() else []
        if not candidatos_busqueda or candidatos_busqueda[0]["puntaje"] < UMBRAL_DEBIL:
            confianza = candidatos_busqueda[0]["puntaje"] if candidatos_busqueda else 0.0
            return _resolver_sin_coincidencia(consulta, confianza)
        confianza = candidatos_busqueda[0]["puntaje"]
        tipo = tipo_del_corpus(candidatos_busqueda[0]["tipo_id"])
        assert tipo is not None  # buscar_local solo devuelve ids del corpus

    candidatos = tipo.variantes_del_citado()
    advertencias = corroboracion + list(tipo.advertencias)

    salida: dict[str, Any] = {
        "estado": "resuelto",
        "tipo_id": tipo.id,
        "tipo_nombre": tipo.nombre,
        "fundamento": tipo.fundamento,
        "naturaleza": tipo.naturaleza.value,
        "normas": list(tipo.normas),
        "confianza_corpus": round(confianza, 3),
        "requiere_desambiguacion": False,
        "eje_desambiguacion": tipo.eje_desambiguacion,
        "pregunta_desambiguacion": "",
        "candidatos": [_variante_a_dict(v, tipo) for v in candidatos],
        # Plazos que corren contra la ENTIDAD, nunca contra el citado. Viajan
        # como contexto para el resumen y jamás pueden ser la respuesta.
        "plazos_de_la_autoridad": [
            {**_variante_a_dict(v, tipo), "uso": "informativo"}
            for v in tipo.variantes_de_la_autoridad()
        ],
        "fuente_verificada": tipo.fuente_verificada,
    }

    # --- elegir la variante -------------------------------------------------
    elegida = tipo.variante(variante_id) if variante_id else None
    if elegida is not None and elegida not in candidatos:
        # El agente apuntó a un plazo de la autoridad: se rechaza y se advierte.
        advertencias.append(
            f"La variante '{elegida.id}' es un plazo de la autoridad, no del "
            f"citado; no puede ser la respuesta."
        )
        elegida = None
    if variante_id and elegida is None and tipo.variante(variante_id) is None:
        advertencias.append(f"La variante '{variante_id}' no existe en este tipo.")

    regla = "plazo_de_la_norma"

    if elegida is None:
        if len(candidatos) == 1:
            elegida = candidatos[0]
        else:
            salida["requiere_desambiguacion"] = True
            salida["pregunta_desambiguacion"] = tipo.pregunta_desambiguacion
            mas_corta = min(candidatos, key=lambda v: v.dias_habiles)
            salida["plazo_mas_corto_de_los_candidatos"] = _variante_a_dict(mas_corta, tipo)

            if tipo.variante_por_defecto is not None:
                elegida = tipo.variante(tipo.variante_por_defecto)
                regla = "defecto_conservador"
            else:
                # Sin defecto honesto (traslado de la demanda: entre 3 y 20 días
                # el procedimiento es un hecho del documento, no algo asumible).
                salida["estado"] = "requiere_desambiguacion"
                salida["dias_habiles_recomendados"] = None
                salida["variante_recomendada"] = None
                salida["regla_aplicada"] = "sin_defecto_debe_resolverse"
                salida["advertencia_calendario"] = False
                salida["texto_advertencia_calendario"] = ""
                advertencias.append(
                    "No hay un plazo por defecto para este tipo: identifique el "
                    "procedimiento en el documento. Si no lo logra, use el "
                    "candidato más corto y declárelo como supuesto en el resumen."
                )
                salida["advertencias"] = advertencias
                return salida

    assert elegida is not None

    # --- prevalencia entre la norma y el plazo escrito en el documento ------
    dias_recomendados = elegida.dias_habiles
    era_calendario_documento = False

    if dias_indicados_en_documento and dias_indicados_en_documento > 0:
        doc_habiles, era_calendario_documento = _dias_del_documento_a_habiles(
            dias_indicados_en_documento, unidad_dias_indicados
        )

        if tipo.naturaleza is NaturalezaPlazo.REFERENCIAL:
            dias_recomendados = doc_habiles
            regla = "plazo_del_documento_prevalece"
            advertencias.append(
                f"El plazo lo fija el oficio ({dias_indicados_en_documento} días); "
                f"los {elegida.dias_habiles} hábiles del corpus son solo el uso típico."
            )

        elif tipo.naturaleza is NaturalezaPlazo.MINIMO_LEGAL:
            dias_recomendados = max(doc_habiles, elegida.dias_habiles)
            regla = "minimo_legal_respetado"
            if doc_habiles < elegida.dias_habiles:
                advertencias.append(
                    f"El documento concede {dias_indicados_en_documento} días, por "
                    f"debajo del mínimo legal: se recomienda el mínimo de la norma."
                )

        elif doc_habiles != elegida.dias_habiles:
            # PERENTORIO: la norma gana, pero la discrepancia se hace visible.
            # Discutible — una orden judicial podría fijar legítimamente otro
            # término — y por eso se advierte en vez de resolverlo en silencio.
            regla = "norma_prevalece_sobre_documento"
            advertencias.append(
                f"El documento menciona {dias_indicados_en_documento} días "
                f"({unidad_dias_indicados or 'unidad no indicada'}) pero la norma "
                f"fija {elegida.dias_habiles} hábiles. Prevalece la norma; "
                f"verifique el documento."
            )

    # --- advertencia de días calendario -------------------------------------
    # El orden importa: si el número recomendado salió del documento y ese
    # documento hablaba en calendario, la advertencia debe citar el documento;
    # citar los días del corpus sería mencionar un número que no se usó.
    if era_calendario_documento and regla in (
        "plazo_del_documento_prevalece",
        "minimo_legal_respetado",
    ):
        salida["advertencia_calendario"] = True
        salida["texto_advertencia_calendario"] = _texto_advertencia_calendario_documento(
            dias_indicados_en_documento or 0, dias_recomendados
        )
    elif elegida.requiere_advertencia_calendario:
        salida["advertencia_calendario"] = True
        salida["texto_advertencia_calendario"] = _texto_advertencia_calendario_norma(
            elegida, tipo
        )
    else:
        salida["advertencia_calendario"] = False
        salida["texto_advertencia_calendario"] = ""

    salida["dias_habiles_recomendados"] = dias_recomendados
    salida["variante_recomendada"] = _variante_a_dict(elegida, tipo)
    salida["regla_aplicada"] = regla
    if elegida.nota:
        advertencias.append(elegida.nota)
    salida["advertencias"] = advertencias

    return salida
