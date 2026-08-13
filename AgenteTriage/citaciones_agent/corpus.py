"""Corpus normativo: los tipos comunes de citación jurídica en Colombia.

ÚNICA FUENTE DE VERDAD de todo número de días y toda norma del proyecto.
``prompts``, ``plazos`` y ``busqueda`` DERIVAN de aquí; nunca repiten un dato.
Si un plazo cambia, se cambia en este archivo y el resto se actualiza solo.

ADVERTENCIA SOBRE LA PROCEDENCIA DE LOS DATOS
    Este corpus lo aportó el usuario del proyecto y NO fue contrastado contra
    fuente oficial. Por eso cada tipo lleva ``fuente_verificada = False``.
    Modificar un plazo es una decisión del dueño del dato, no solo un cambio de
    código — mismo criterio que la lista blanca de ProyectoEDCO.

PRINCIPIO QUE GOBIERNA EL DISEÑO: conservador significa MENOS días. Son plazos
perentorios; sobreestimarlos hace que el usuario pierda el término (daño
irreversible), subestimarlos solo le cuesta urgencia. De ahí el piso en la
conversión calendario→hábiles, la elección de variante por defecto y la regla
"ante la duda, el plazo más corto" del prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from citaciones_agent.schemas import NaturalezaPlazo, SujetoPlazo, UnidadPlazo
from citaciones_agent.texto import normalizar, tokenizar

DIAS_HABILES_POR_SEMANA = 5
DIAS_POR_SEMANA = 7


def calendario_a_habiles(dias_calendario: int) -> int:
    """Convierte días CALENDARIO a HÁBILES de forma conservadora (a la baja).

    Piso (``//``) y no ``round`` ni ``ceil``, por tres razones:

    1. Es un plazo perentorio: el error tiene que sesgarse hacia menos días.
    2. La razón 5/7 asume que solo el fin de semana es inhábil. Colombia tiene
       ~18 festivos al año, así que los hábiles REALES son menos que 5/7 de los
       calendario; el piso compensa parcialmente ese optimismo estructural.
    3. Es determinístico: sin calendario de festivos, sin fecha de inicio y sin
       aritmética del modelo.

    LIMITACIÓN: no considera festivos. 15 días calendario que crucen Semana
    Santa pueden ser 9 hábiles reales, no 10. La advertencia que acompaña a los
    plazos en calendario lo dice explícitamente.

    >>> calendario_a_habiles(15)
    10
    """
    if dias_calendario <= 0:
        return 0
    # max(1, ...) es defensivo: 1 día calendario daría 0, y un plazo de cero
    # días no es accionable. Ningún dato del corpus llega a ese caso.
    return max(1, (dias_calendario * DIAS_HABILES_POR_SEMANA) // DIAS_POR_SEMANA)


@dataclass(frozen=True)
class VarianteCitacion:
    """Un plazo concreto dentro de un tipo de citación.

    Todo tipo se modela SIEMPRE con variantes, incluso los de plazo único, para
    que ``plazos`` y ``prompts`` nunca tengan que ramificar entre "tipo con int
    plano" y "tipo con condicionales". Forma uniforme = menos bugs.
    """

    id: str
    acto: str                      # qué se hace en ese plazo ("Objetar el comparendo")
    condicion: str                 # cuándo aplica esta variante; "" si es la única
    dias: int                      # tal como lo dice la norma, SIN convertir
    unidad: UnidadPlazo
    sujeto: SujetoPlazo
    fundamento: str = ""           # artículo específico; "" hereda el del tipo
    nota: str = ""

    @property
    def dias_habiles(self) -> int:
        """Plazo normalizado a días hábiles. ÚNICA puerta de la conversión.

        Que sea una property y no un campo es deliberado: no existe forma de
        leer un plazo del corpus y olvidarse de convertirlo. Quien quiera el
        número literal de la norma tiene que pedir ``dias`` explícitamente.
        """
        if self.unidad is UnidadPlazo.HABILES:
            return self.dias
        return calendario_a_habiles(self.dias)

    @property
    def requiere_advertencia_calendario(self) -> bool:
        return self.unidad is UnidadPlazo.CALENDARIO

    def descripcion_corta(self) -> str:
        partes = [f"{self.acto}: {self.dias} días {self.unidad.value}"]
        if self.unidad is UnidadPlazo.CALENDARIO:
            partes.append(f"(= {self.dias_habiles} hábiles)")
        if self.condicion:
            partes.append(f"— {self.condicion}")
        return " ".join(partes)


@dataclass(frozen=True)
class TipoCitacion:
    """Un tipo de citación del corpus, con todas sus variantes de plazo."""

    id: str
    nombre: str
    descripcion: str
    fundamento: str
    naturaleza: NaturalezaPlazo
    variantes: tuple[VarianteCitacion, ...]
    palabras_clave: tuple[str, ...] = ()     # términos DIAGNÓSTICOS (peso alto)
    frases_clave: tuple[str, ...] = ()       # multi-palabra: la señal más fuerte
    normas: tuple[str, ...] = ()             # variantes de cita para emparejar
    eje_desambiguacion: str = ""
    pregunta_desambiguacion: str = ""
    variante_por_defecto: str | None = None  # None => obliga a resolver la variante
    advertencias: tuple[str, ...] = ()
    fuente_verificada: bool = False

    def variantes_del_citado(self) -> tuple[VarianteCitacion, ...]:
        return tuple(v for v in self.variantes if v.sujeto is SujetoPlazo.CITADO)

    def variantes_de_la_autoridad(self) -> tuple[VarianteCitacion, ...]:
        return tuple(v for v in self.variantes if v.sujeto is SujetoPlazo.AUTORIDAD)

    def variante(self, variante_id: str) -> VarianteCitacion | None:
        return next((v for v in self.variantes if v.id == variante_id), None)

    def plazo_conservador(self) -> VarianteCitacion | None:
        """La variante del citado con MENOS días hábiles."""
        candidatas = self.variantes_del_citado()
        return min(candidatas, key=lambda v: v.dias_habiles) if candidatas else None

    def fundamento_de(self, variante: VarianteCitacion) -> str:
        return variante.fundamento or self.fundamento


# ---------------------------------------------------------------------------
# El corpus. Claves con prefijo ``cit_``, en espejo de las ``wl_`` de EDCO.
# ---------------------------------------------------------------------------

_TIPOS: tuple[TipoCitacion, ...] = (
    TipoCitacion(
        id="cit_notificacion_personal_civil",
        nombre="Citación para notificación personal en proceso judicial civil",
        descripcion=(
            "Citatorio que envía el juzgado para que el demandado comparezca a "
            "notificarse personalmente del auto admisorio de la demanda. Vencido "
            "el plazo se pasa a notificación por aviso."
        ),
        fundamento="Código General del Proceso (CGP), arts. 291-292",
        naturaleza=NaturalezaPlazo.PERENTORIO,
        variantes=(
            VarianteCitacion(
                id="v_misma_ciudad",
                acto="Comparecer a notificarse personalmente",
                condicion="el citado reside en la misma ciudad del juzgado",
                dias=5, unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
            ),
            VarianteCitacion(
                id="v_otro_municipio",
                acto="Comparecer a notificarse personalmente",
                condicion="el citado recibe la comunicación en otro municipio",
                dias=10, unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
            ),
            VarianteCitacion(
                id="v_exterior",
                acto="Comparecer a notificarse personalmente",
                condicion="el citado está en el exterior",
                dias=30, unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
            ),
        ),
        palabras_clave=(
            "citatorio", "comparecer", "notificarse", "juzgado", "demandado",
            "admisorio", "aviso", "secretaria",
        ),
        frases_clave=(
            "notificacion personal", "auto admisorio", "notificacion por aviso",
            "citatorio para notificacion", "comparecer al juzgado",
        ),
        normas=("cgp", "codigo general del proceso", "art. 291", "art. 292",
                "articulo 291", "articulo 292"),
        eje_desambiguacion="ubicacion_del_citado",
        pregunta_desambiguacion=(
            "¿Dónde recibe la comunicación el citado: en la misma ciudad del "
            "juzgado, en otro municipio del país, o en el exterior?"
        ),
        # Las variantes son un espectro sobre un mismo hecho, así que quedarse
        # corto es seguro: se asume la hipótesis más exigente.
        variante_por_defecto="v_misma_ciudad",
        advertencias=(
            "Vencido el plazo sin comparecer se procede a notificación por aviso: "
            "es una consecuencia, NO una prórroga del término.",
        ),
    ),
    TipoCitacion(
        id="cit_traslado_demanda",
        nombre="Traslado de la demanda (plazo para contestar)",
        descripcion=(
            "Una vez notificado, el demandado tiene un plazo para contestar que "
            "depende del tipo de proceso. Todos los plazos se cuentan en días "
            "hábiles, sin sábados, domingos ni festivos."
        ),
        fundamento="CGP, arts. 369, 391, 399, 402, 409, 421, 442",
        naturaleza=NaturalezaPlazo.PERENTORIO,
        variantes=(
            VarianteCitacion(
                id="v_verbal", acto="Contestar la demanda",
                condicion="proceso verbal", dias=20,
                unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
                fundamento="CGP art. 369",
            ),
            VarianteCitacion(
                id="v_verbal_sumario", acto="Contestar la demanda",
                condicion="proceso verbal sumario", dias=10,
                unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
                fundamento="CGP art. 391",
            ),
            VarianteCitacion(
                id="v_expropiacion", acto="Contestar la demanda",
                condicion="proceso de expropiación", dias=3,
                unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
                fundamento="CGP art. 399",
            ),
            VarianteCitacion(
                id="v_deslinde", acto="Contestar la demanda",
                condicion="proceso de deslinde y amojonamiento", dias=3,
                unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
                fundamento="CGP art. 402",
            ),
            VarianteCitacion(
                id="v_divisorio", acto="Contestar la demanda",
                condicion="proceso divisorio", dias=10,
                unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
                fundamento="CGP art. 409",
            ),
            VarianteCitacion(
                id="v_monitorio", acto="Contestar la demanda",
                condicion="proceso monitorio", dias=10,
                unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
                fundamento="CGP art. 421",
            ),
            VarianteCitacion(
                id="v_ejecutivo", acto="Proponer excepciones",
                condicion="proceso ejecutivo", dias=10,
                unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
                fundamento="CGP art. 442",
                nota=(
                    "Son 10 días hábiles para PROPONER EXCEPCIONES, no una "
                    "contestación en sentido estricto."
                ),
            ),
        ),
        palabras_clave=(
            "traslado", "contestar", "contestacion", "demanda", "demandado",
            "excepciones", "ejecutivo", "verbal", "sumario", "monitorio",
            "divisorio", "expropiacion", "deslinde", "amojonamiento",
        ),
        frases_clave=(
            "traslado de la demanda", "contestar la demanda", "mandamiento de pago",
            "proceso verbal sumario", "proceso ejecutivo", "proponer excepciones",
            "termino para contestar",
        ),
        normas=("cgp", "codigo general del proceso", "art. 369", "art. 391",
                "art. 399", "art. 402", "art. 409", "art. 421", "art. 442"),
        eje_desambiguacion="tipo_de_proceso",
        pregunta_desambiguacion=(
            "¿Qué tipo de proceso es: verbal, verbal sumario, ejecutivo, "
            "monitorio, divisorio, de expropiación, o de deslinde y amojonamiento?"
        ),
        # A propósito SIN defecto: entre 3 y 20 días no hay elección honesta.
        # El procedimiento es un hecho declarado en el documento, no una
        # circunstancia que se pueda asumir; defectear a 3 sería engañoso y
        # defectear a 20 sería peligroso.
        variante_por_defecto=None,
        advertencias=(
            "Los plazos corren en días hábiles: no cuentan sábados, domingos ni "
            "festivos.",
        ),
    ),
    TipoCitacion(
        id="cit_conciliacion_extrajudicial",
        nombre="Citación a audiencia de conciliación extrajudicial",
        descripcion=(
            "Recibida la solicitud, el conciliador fija fecha y hora de la "
            "audiencia. La citación no otorga al citado un plazo para responder: "
            "le señala una FECHA para comparecer."
        ),
        fundamento="Ley 2220 de 2022 (Estatuto de Conciliación)",
        naturaleza=NaturalezaPlazo.PERENTORIO,
        variantes=(
            VarianteCitacion(
                id="v_fijar_fecha", acto="Fijar fecha y hora de la audiencia",
                condicion="corre contra el conciliador desde la solicitud",
                dias=10, unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.AUTORIDAD,
                nota="El dato de origen no califica la unidad; se asume hábiles.",
            ),
            VarianteCitacion(
                id="v_celebrar_audiencia", acto="Celebrar la audiencia",
                condicion="contado desde la admisión de la solicitud",
                dias=30, unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.AUTORIDAD,
                nota="El dato de origen no califica la unidad; se asume hábiles.",
            ),
            VarianteCitacion(
                id="v_justificar_inasistencia",
                acto="Justificar la inasistencia a la audiencia",
                condicion="si la parte citada no asistió",
                dias=3, unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
            ),
        ),
        palabras_clave=(
            "conciliacion", "conciliador", "audiencia", "solicitud",
            "inasistencia", "convocado", "convocante",
        ),
        frases_clave=(
            "audiencia de conciliacion", "conciliacion extrajudicial",
            "centro de conciliacion", "justificar la inasistencia",
            "conciliacion en derecho",
        ),
        normas=("ley 2220 de 2022", "ley 2220", "ley 640 de 2001",
                "estatuto de conciliacion"),
        variante_por_defecto="v_justificar_inasistencia",
        advertencias=(
            "Una citación a conciliación NO otorga un plazo en días para "
            "responder: señala una FECHA de audiencia a la que hay que "
            "comparecer. El único término en días que corre contra el citado es "
            "el de 3 días hábiles para justificar la inasistencia, que es un "
            "supuesto distinto. Verifique la fecha de audiencia en el documento.",
        ),
    ),
    TipoCitacion(
        id="cit_actuacion_administrativa_cpaca",
        nombre="Citación / notificación en una actuación administrativa",
        descripcion=(
            "Cuando una entidad pública expide un acto que afecta al ciudadano "
            "(resolución, sanción), le envía citación para notificación personal. "
            "Notificado el acto, el ciudadano puede interponer recursos."
        ),
        fundamento="CPACA (Ley 1437 de 2011), arts. 67-69 y 76",
        naturaleza=NaturalezaPlazo.PERENTORIO,
        variantes=(
            VarianteCitacion(
                id="v_envio_citacion",
                acto="Enviar la citación para notificación personal",
                condicion="corre contra la entidad desde la expedición del acto",
                dias=5, unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.AUTORIDAD,
                fundamento="CPACA arts. 67-68",
                nota=(
                    "El dato de origen no califica la unidad; se asume hábiles. "
                    "Vencido, procede notificación por aviso."
                ),
            ),
            VarianteCitacion(
                id="v_recursos",
                acto="Interponer recursos de reposición o apelación",
                condicion="contado desde la notificación del acto",
                dias=10, unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
                fundamento="CPACA art. 76",
            ),
        ),
        palabras_clave=(
            "resolucion", "recursos", "reposicion", "apelacion", "entidad",
            "administrativo", "notificacion", "acto", "superintendencia",
            "alcaldia", "secretaria",
        ),
        frases_clave=(
            "actuacion administrativa", "recurso de reposicion",
            "recurso de apelacion", "acto administrativo", "via gubernativa",
            "notificacion personal del acto",
        ),
        normas=("cpaca", "ley 1437 de 2011", "ley 1437", "art. 67", "art. 68",
                "art. 69", "art. 76", "codigo de procedimiento administrativo"),
        variante_por_defecto="v_recursos",
        advertencias=(
            "Los 5 días del envío de la citación corren contra la ENTIDAD, no "
            "contra el ciudadano: no confundirlos con el plazo de respuesta.",
        ),
    ),
    TipoCitacion(
        id="cit_requerimiento_dian",
        nombre="Requerimiento ordinario de información de la DIAN",
        descripcion=(
            "Requerimiento tributario para que el contribuyente aporte "
            "información. A diferencia del resto del corpus, el plazo se cuenta "
            "en días CALENDARIO, y la norma fija un mínimo: la DIAN puede "
            "conceder más, nunca menos."
        ),
        fundamento="Estatuto Tributario, art. 261 (Ley 223 de 1995)",
        naturaleza=NaturalezaPlazo.MINIMO_LEGAL,
        variantes=(
            VarianteCitacion(
                id="v_requerimiento_ordinario",
                acto="Responder el requerimiento ordinario de información",
                condicion="",
                dias=15, unidad=UnidadPlazo.CALENDARIO, sujeto=SujetoPlazo.CITADO,
                nota="Plazo MÍNIMO legal; el requerimiento puede conceder más.",
            ),
        ),
        palabras_clave=(
            "dian", "requerimiento", "contribuyente", "tributario", "impuestos",
            "rut", "renta", "fiscalizacion", "informacion",
        ),
        frases_clave=(
            "requerimiento ordinario de informacion", "requerimiento ordinario",
            "direccion de impuestos y aduanas", "estatuto tributario",
            "requerimiento especial",
        ),
        normas=("estatuto tributario", "e.t.", "art. 261", "articulo 261",
                "ley 223 de 1995"),
        variante_por_defecto="v_requerimiento_ordinario",
        advertencias=(
            "Es un plazo MÍNIMO: si el requerimiento concede más días, prevalece "
            "el del documento.",
        ),
    ),
    TipoCitacion(
        id="cit_audiencia_comparendo_policia",
        nombre="Citación a audiencia pública por comparendo (Código de Policía)",
        descripcion=(
            "Conocida la querella o el comportamiento contrario a la convivencia, "
            "la autoridad cita a audiencia pública. Quien recibió un comparendo y "
            "quiere objetarlo debe acudir ante la Inspección de Policía de la "
            "jurisdicción donde ocurrieron los hechos."
        ),
        fundamento="Ley 1801 de 2016 (Código Nacional de Policía), art. 223",
        naturaleza=NaturalezaPlazo.PERENTORIO,
        variantes=(
            VarianteCitacion(
                id="v_citar_audiencia", acto="Citar a audiencia pública",
                condicion="corre contra la autoridad desde que conoce la querella",
                dias=5, unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.AUTORIDAD,
                nota="El dato de origen no califica la unidad; se asume hábiles.",
            ),
            VarianteCitacion(
                id="v_objetar_comparendo", acto="Objetar el comparendo",
                condicion="ante la Inspección de Policía de la jurisdicción",
                dias=3, unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
            ),
        ),
        palabras_clave=(
            "comparendo", "policia", "convivencia", "querella", "infractor",
            "querellante", "objetar", "inspeccion",
        ),
        frases_clave=(
            "inspeccion de policia", "audiencia publica", "codigo de policia",
            "comportamiento contrario a la convivencia", "orden de comparendo",
            "objetar el comparendo",
        ),
        normas=("ley 1801 de 2016", "ley 1801", "art. 223", "articulo 223",
                "codigo nacional de policia", "codigo nacional de seguridad y convivencia"),
        variante_por_defecto="v_objetar_comparendo",
        advertencias=(
            "Los 3 días hábiles para objetar son muy cortos y corren desde la "
            "imposición del comparendo.",
        ),
    ),
    TipoCitacion(
        id="cit_inspeccion_mintrabajo",
        nombre="Requerimiento de inspección del Ministerio del Trabajo",
        descripcion=(
            "Oficio de un inspector de trabajo a la empresa (por ejemplo, la "
            "lista de chequeo de estándares del SG-SST) para que diligencie y "
            "remita información con sus soportes. El plazo lo fija el propio "
            "oficio; 10 días hábiles es el uso típico."
        ),
        fundamento=(
            "Normativa de inspección, vigilancia y control laboral "
            "(p. ej. Resolución 0312 de 2019 en materia de SG-SST). "
            "El plazo concreto lo fija el oficio del inspector."
        ),
        naturaleza=NaturalezaPlazo.REFERENCIAL,
        variantes=(
            VarianteCitacion(
                id="v_respuesta_oficio",
                acto="Diligenciar y remitir la información con sus soportes",
                condicion="contado desde el recibo del oficio",
                dias=10, unidad=UnidadPlazo.HABILES, sujeto=SujetoPlazo.CITADO,
                nota=(
                    "Uso típico, NO un plazo legal fijo: puede variar según el "
                    "tipo de requerimiento y lo que fije el inspector."
                ),
            ),
        ),
        palabras_clave=(
            "inspector", "inspeccion", "trabajo", "laboral", "empresa",
            "empleador", "soportes", "sst", "requerimiento",
        ),
        frases_clave=(
            "ministerio del trabajo", "inspector de trabajo", "sg-sst",
            "seguridad y salud en el trabajo", "lista de chequeo",
            "estandares minimos",
        ),
        normas=("resolucion 0312 de 2019", "resolucion 0312", "ministerio del trabajo"),
        variante_por_defecto="v_respuesta_oficio",
        advertencias=(
            "El plazo lo fija el oficio del inspector: si el documento señala un "
            "término, ese prevalece sobre los 10 días típicos.",
        ),
    ),
)

CORPUS_CITACIONES: dict[str, TipoCitacion] = {tipo.id: tipo for tipo in _TIPOS}


# ---------------------------------------------------------------------------
# Derivados, calculados al importar. Esto es lo que hace imposible que el
# prompt, el buscador y el resolvedor de plazos se desincronicen del corpus.
# ---------------------------------------------------------------------------

def _plazos_de_referencia() -> tuple[int, ...]:
    """Los plazos en hábiles que existen en el corpus, ordenados y sin repetir.

    Sirven de anclas numéricas para la ruta "ningún tipo coincide": le dan al
    agente magnitudes plausibles SIN afirmar ninguna norma nueva, porque todas
    salen del propio corpus.
    """
    return tuple(sorted({v.dias_habiles for t in _TIPOS for v in t.variantes}))


PLAZOS_DE_REFERENCIA: tuple[int, ...] = _plazos_de_referencia()

TIPOS_CON_ADVERTENCIA_CALENDARIO: tuple[str, ...] = tuple(
    t.id for t in _TIPOS
    if any(v.requiere_advertencia_calendario for v in t.variantes)
)


def _indice_senales_proceso() -> tuple[tuple[str, str, str], ...]:
    """Frases que delatan una variante concreta -> (frase, tipo_id, variante_id).

    ORDENADO POR LONGITUD DESCENDENTE, y ese orden es load-bearing: si se prueba
    "verbal" antes que "verbal sumario", todo proceso verbal sumario se
    clasifica como verbal y el plazo se duplica de 10 a 20 días. Igual con
    "requerimiento" antes que "requerimiento ordinario".
    """
    entradas: list[tuple[str, str, str]] = []
    for tipo in _TIPOS:
        for variante in tipo.variantes:
            if variante.condicion:
                entradas.append((normalizar(variante.condicion), tipo.id, variante.id))
    return tuple(sorted(entradas, key=lambda e: len(e[0]), reverse=True))


INDICE_SENALES_PROCESO: tuple[tuple[str, str, str], ...] = _indice_senales_proceso()


def _stopwords_del_dominio(umbral: int = 4) -> frozenset[str]:
    """Tokens presentes en >= ``umbral`` de los tipos: no distinguen nada.

    Autocalculado a propósito. "citacion" o "plazo" aparecen en más de la mitad
    del corpus, así que emparejarlos no aporta señal — y una lista mantenida a
    mano se desactualizaría en cuanto se agregue un tipo nuevo.

    El umbral es 4 sobre 7 (mayoría simple). Con 5 se escapaba "citacion", que
    es precisamente el token menos diagnóstico posible: los siete documentos SON
    citaciones.
    """
    conteo: dict[str, int] = {}
    for tipo in _TIPOS:
        presentes = tokenizar(f"{tipo.nombre} {tipo.descripcion}")
        for token in presentes:
            conteo[token] = conteo.get(token, 0) + 1
    return frozenset(token for token, n in conteo.items() if n >= umbral)


STOPWORDS_DEL_DOMINIO: frozenset[str] = _stopwords_del_dominio()


def tipo(tipo_id: str) -> TipoCitacion | None:
    """Acceso por id, tolerante a un id inexistente (el agente puede inventarlo)."""
    return CORPUS_CITACIONES.get(tipo_id)


def ids_validos() -> tuple[str, ...]:
    return tuple(CORPUS_CITACIONES)


def todos() -> Iterable[TipoCitacion]:
    return _TIPOS
