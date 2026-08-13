"""Demo del agente de citaciones vía la API de Gemini.

Corre cuatro citaciones SINTÉTICAS que ejercitan los casos interesantes:
notificación personal civil (sub-variante por ubicación), requerimiento DIAN
(el único plazo en días calendario), comparendo de policía (plazo muy corto del
citado frente al de la autoridad) y una citación que no está en el corpus.

Requiere GOOGLE_API_KEY como variable de entorno o en el ``.env`` de la raíz.

Ejecutar desde la raíz del proyecto:
    venv\\Scripts\\python.exe examples/demo_citaciones.py
"""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

# Permite ejecutar el script sin instalar el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from citaciones_agent.agente import construir_agente_citaciones
from citaciones_agent.config import LIMITE_RECURSION, MODELO
from citaciones_agent.prompts import formatear_entrada

CITACION_CIVIL = """JUZGADO DOCE CIVIL MUNICIPAL DE BOGOTÁ D.C.
Radicado No. 11001-40-03-012-2026-00456-00

CITATORIO PARA NOTIFICACIÓN PERSONAL
(Artículos 291 y 292 del Código General del Proceso)

Bogotá D.C., 12 de marzo de 2026

Señor
JUAN CARLOS PÉREZ GÓMEZ
Dirección: Calle 45 No. 13-22, Tunja (Boyacá)

Por medio del presente se le CITA para que comparezca a este Despacho con el fin
de notificarse personalmente del auto admisorio de la demanda proferido dentro
del proceso de la referencia.

Vencido el término sin que comparezca, se procederá a la notificación por aviso
de que trata el artículo 292 del CGP.
"""

CITACION_DIAN = """DIRECCIÓN DE IMPUESTOS Y ADUANAS NACIONALES - DIAN
Subdirección de Fiscalización Tributaria

REQUERIMIENTO ORDINARIO DE INFORMACIÓN No. 2026-0000871

Bogotá D.C., 03 de abril de 2026

Contribuyente: INVERSIONES EL ROBLE S.A.S. — NIT 900.123.456-7

En ejercicio de las facultades del artículo 261 del Estatuto Tributario, se le
requiere para que aporte la información relacionada en el anexo del presente
acto administrativo.
"""

CITACION_COMPARENDO = """ALCALDÍA DE MEDELLÍN
INSPECCIÓN DE POLICÍA URBANA 4

ORDEN DE COMPARENDO No. 05001-2026-33412
Medellín, 22 de mayo de 2026

Se le informa al presunto infractor que puede objetar el comparendo impuesto por
comportamiento contrario a la convivencia, ante la Inspección de Policía de la
jurisdicción donde ocurrieron los hechos, conforme al artículo 223 de la
Ley 1801 de 2016.
"""

CITACION_FUERA_DEL_CORPUS = """COPROPIEDAD EDIFICIO LOS ALMENDROS
Consejo de Administración — Régimen de Propiedad Horizontal (Ley 675 de 2001)

Bogotá D.C., 2 de junio de 2026

Se cita al propietario de la unidad privada 302 para que se pronuncie sobre el
requerimiento de pago de las cuotas de administración en mora, antes de que el
Consejo remita el asunto a cobro jurídico.
"""

CASOS = (
    ("Notificación personal civil (CGP 291-292)", CITACION_CIVIL),
    ("Requerimiento DIAN (E.T. art. 261, días CALENDARIO)", CITACION_DIAN),
    ("Comparendo de policía (Ley 1801, art. 223)", CITACION_COMPARENDO),
    ("Fuera del corpus (propiedad horizontal)", CITACION_FUERA_DEL_CORPUS),
)


def _verificar_clave() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    clave = os.environ.get("GOOGLE_API_KEY", "")
    if not clave or clave.startswith("REEMPLAZA"):
        raise SystemExit(
            "Falta GOOGLE_API_KEY. Defínala como variable de entorno o copie "
            ".env.example a .env y ponga su clave de la API de Gemini."
        )


def _contenido_como_dict(contenido) -> dict | None:
    """Recupera el dict que devolvió una herramienta desde el ToolMessage.

    LangChain serializa el retorno con ``str()``, que produce repr de Python
    (comillas simples), no JSON. Se intentan ambos y si nada funciona se
    devuelve None: es solo para la traza del demo, no debe tumbar la corrida.
    """
    if isinstance(contenido, dict):
        return contenido
    if not isinstance(contenido, str):
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            valor = parser(contenido)
            return valor if isinstance(valor, dict) else None
        except (ValueError, SyntaxError, TypeError):
            continue
    return None


def _traza(mensajes: list) -> int | None:
    """Imprime las llamadas a herramientas y devuelve el plazo recomendado.

    El plazo recomendado sirve para el chequeo blando de abajo: comparar lo que
    la herramienta calculó contra lo que el modelo finalmente reportó.
    """
    recomendado: int | None = None

    for mensaje in mensajes:
        for llamada in getattr(mensaje, "tool_calls", None) or []:
            argumentos = {
                k: (v[:60] + "…" if isinstance(v, str) and len(v) > 60 else v)
                for k, v in (llamada.get("args") or {}).items()
            }
            print(f"    -> {llamada.get('name')}({argumentos})")

        if type(mensaje).__name__ != "ToolMessage":
            continue

        datos = _contenido_como_dict(getattr(mensaje, "content", None))
        if not datos:
            continue

        # Traza de search: los puntajes son lo que permite calibrar los umbrales.
        if "fuerza" in datos:
            top = (datos.get("resultados") or [{}])[0]
            print(
                f"       search: fuerza={datos['fuerza']} "
                f"top={top.get('tipo_id')} puntaje={top.get('puntaje')}"
            )
            if datos.get("respaldo_web"):
                print(f"       respaldo_web: {datos['respaldo_web'].get('estado')}")

        # Traza de time_determination.
        if "dias_habiles_recomendados" in datos:
            recomendado = datos["dias_habiles_recomendados"]
            print(
                f"       time_determination: estado={datos.get('estado')} "
                f"dias={recomendado} regla={datos.get('regla_aplicada')} "
                f"calendario={datos.get('advertencia_calendario')}"
            )
            for advertencia in datos.get("advertencias") or []:
                print(f"         ! {advertencia}")

    return recomendado


def main() -> None:
    _verificar_clave()
    agente = construir_agente_citaciones()
    print(f"Modelo: {MODELO}\n")

    for titulo, citacion in CASOS:
        print("=" * 78)
        print(titulo)
        print("=" * 78)

        try:
            salida = agente.invoke(
                {"messages": [{"role": "user", "content": formatear_entrada(citacion)}]},
                config={"recursion_limit": LIMITE_RECURSION},
            )
        except Exception as exc:  # amplio: una citación fallida no debe abortar el demo
            print(f"  ERROR en la corrida: {type(exc).__name__}: {exc}\n")
            continue

        recomendado = _traza(salida.get("messages") or [])

        resultado = salida.get("structured_response")
        if resultado is None:
            # La clave es NotRequired: si se agotó el tope de llamadas del
            # middleware, la corrida termina sin salida estructurada.
            print(
                "  SIN SALIDA ESTRUCTURADA: probablemente se alcanzó el tope de "
                "llamadas al modelo. Revise LIMITE_LLAMADAS_MODELO en config.py.\n"
            )
            continue

        print("\n  RESULTADO:")
        print(
            "  "
            + json.dumps(resultado.model_dump(), ensure_ascii=False, indent=2).replace(
                "\n", "\n  "
            )
        )

        # Chequeo BLANDO, no un gate: los plazos son rangos y la decisión final
        # es del agente. Solo se hace visible la discrepancia para el humano.
        if recomendado is not None and resultado.dias_habiles != recomendado:
            print(
                f"\n  AVISO: el agente reportó {resultado.dias_habiles} días pero la "
                f"herramienta calculó {recomendado}. Revise si la desviación está "
                f"justificada en el resumen."
            )
        print()


if __name__ == "__main__":
    main()
