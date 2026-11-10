#!/usr/bin/env python3
"""enrutar — elige la skill del toolkit para una petición del usuario con JEV (AGENT §5b).

Para un orquestador barato, acertar la herramienta al inicio ahorra turnos (el costo que domina es la
sesión del agente). Una decisión `choice` de JEV cuesta ~0.00003 USD y devuelve probabilidades por
opción; si la elegida no es clara, se le pide al agente que pregunte al usuario entre las dos mejores.

Uso:
  python3 scripts/enrutar.py "Quiero un video tipo reel con fotos de la expo y voz"
  python3 scripts/enrutar.py "…" --log proyectos/<slug>/recursos/costos.jsonl

Salida (≤6 líneas): ruta elegida con su probabilidad, skill de SKILL.md y los comandos siguientes.
Códigos: 0 ok · 2 petición vacía · 4 falla de la API.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decision  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Opciones que ve JEV (descripción) y lo que se le indica al agente (skill + comandos).
RUTAS = {
    "promo_ui": {
        "desc": "Video promo vertical de un producto/servicio con UI de app animada (chat, WhatsApp, "
                "tarjetas, teléfono), intro y cierre con llamada a la acción; estilo de la casa.",
        "skill": "promo-ui",
        "pasos": ["python3 scripts/promo.py nuevo <slug>", "python3 scripts/promo.py ayuda",
                  "editar promo.json → python3 scripts/promo.py validar <proyecto>", "python3 scripts/promo.py todo <proyecto>"],
    },
    "curso": {
        "desc": "Curso o capacitación en video: varias lecciones narradas con objetivos de aprendizaje, módulos, "
                "preguntas intercaladas, evaluación y carta descriptiva; no es un video suelto ni un reel.",
        "skill": "crear-curso",
        "pasos": ["python3 scripts/curso.py nuevo <slug>", "editar curso.json → python3 scripts/curso.py validar <proyecto>",
                  "python3 scripts/curso.py todo <proyecto> --qa"],
    },
    "remotion_video": {
        "desc": "Video con motion graphics a la medida (gráficas animadas desde datos, Lottie, mapas, layouts con "
                "metraje real, tipografía cinética) que NO es un promo con la UI de la casa ni un reel de fotos; "
                "se programa como composición React (Remotion).",
        "skill": "remotion-video",
        "pasos": ["python3 scripts/remotion.py nuevo <slug>",
                  "editar remotion.json y el TSX (skills /remotion-markup) → python3 scripts/remotion.py validar <proyecto>",
                  "python3 scripts/remotion.py render <proyecto>"],
    },
    "reel_fotos": {
        "desc": "Reel vertical narrado hecho con fotos o imágenes (Ken Burns, mosaicos, logos), con voz y música.",
        "skill": "armar-reel",
        "pasos": ["copiar scripts/reel.ejemplo.json a proyectos/<slug>_<DDMMAAAA>/reel.json",
                  "python3 scripts/reel.py --spec proyectos/<slug>_<DDMMAAAA>/reel.json todo"],
    },
    "subtitulos": {
        "desc": "Agregar o generar subtítulos (SRT/VTT o quemados) a un video o audio existente.",
        "skill": "crear-subtitulos",
        "pasos": ["python3 scripts/subtitulos.py <video> --quemar"],
    },
    "traducir_pantalla": {
        "desc": "Traducir o cambiar el texto que ya viene incrustado (rótulos en pantalla) de un video "
                "existente, sin agregar subtítulos; conserva el audio y la duración. Incluye descargar "
                "un video de YouTube para editarlo.",
        "skill": "traducir-texto-en-pantalla / descargar-video-youtube",
        "pasos": ["yt-dlp -f \"bv*+ba/b\" --merge-output-format mp4 -o recursos/origen.%(ext)s <url>",
                  "python3 scripts/pantalla.py detectar <video> --json caps.json",
                  "editar caps.json (lineas) → python3 scripts/pantalla.py generar caps.json --render"],
    },
    "quitar_silencios": {
        "desc": "Cortar tiempos muertos o silencios de un video o audio existente.",
        "skill": "quitar-silencios",
        "pasos": ["python3 scripts/silencios.py <video> --reporte", "python3 scripts/silencios.py <video>"],
    },
    "voz": {
        "desc": "Generar una voz en off / locución (TTS) o clonar una voz, sin armar video.",
        "skill": "crear-audio",
        "pasos": ["ver la skill crear-audio de SKILL.md (OpenRouter gpt-audio-mini; ElevenLabs solo si aplica)"],
    },
    "imagen": {
        "desc": "Crear una imagen, banner o botón (estático), no un video.",
        "skill": "crear-imagen",
        "pasos": ["ver la skill crear-imagen de SKILL.md (ilustración sin texto + drawtext local)"],
    },
    "editar_video": {
        "desc": "Edición básica de video existente: cortar, unir clips, transiciones, marca de agua, "
                "quitar ruido, convertir formato o resolución.",
        "skill": "cortar-video / unir-clips / transiciones / convertir-formato",
        "pasos": ["FFmpeg directo según la skill correspondiente de SKILL.md"],
    },
    "musica_sfx": {
        "desc": "Conseguir música o efectos de sonido libres de derechos (CC0).",
        "skill": "Audio CC0 (docs/Audio-CC0.md)",
        "pasos": ["python3 scripts/fetch_audio.py \"<búsqueda>\" -n 5 --profile sfx|bgm"],
    },
}


def preguntas():
    return {
        "ruta": {
            "type": "choice",
            "instructions": "Elige la herramienta del toolkit de edición de video que resuelve la petición del "
                            "usuario. Si pide un curso, capacitación o lecciones con evaluación, es curso; si pide un video promo con interfaz de app o chat animado, es promo_ui; si es "
                            "un reel hecho con fotos, es reel_fotos; si pide subtítulos o quitar silencios a un "
                            "video existente, elige esa operación; si pide traducir o cambiar el texto que ya viene "
                            "en pantalla (o bajar un video de YouTube para editarlo), es traducir_pantalla; si pide motion "
                            "graphics a la medida (gráficas animadas desde datos, Lottie, mapas, metraje real con "
                            "animación) que no es la UI de la casa, es remotion_video.",
            "criteria": {k: v["desc"] for k, v in RUTAS.items()},
        }
    }


def interpretar(res):
    """(elegida, prob, segunda, prob2) a partir de la respuesta de JEV."""
    a = (res.get("answers") or {}).get("ruta") or {}
    probs = a.get("probabilities") or {}
    orden = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    elegida = a.get("choice") or (orden[0][0] if orden else None)
    p1 = probs.get(elegida, 0.0)
    segunda = next(((k, v) for k, v in orden if k != elegida), (None, 0.0))
    return elegida, p1, segunda[0], segunda[1]


def main():
    ap = argparse.ArgumentParser(description="Elige la skill del toolkit para una petición (JEV)")
    ap.add_argument("peticion", nargs="+", help="texto de la petición del usuario")
    ap.add_argument("--log", help="costos.jsonl donde registrar la llamada (AGENT §10); por defecto "
                                  "proyectos/_enrutador/recursos/costos.jsonl (aún no hay proyecto)")
    ap.add_argument("--umbral", type=float, default=0.55, help="probabilidad mínima para decidir sin preguntar")
    a = ap.parse_args()
    texto = " ".join(a.peticion).strip()
    if not texto:
        print("ERROR petición vacía.")
        return 2
    # AGENT §5b: toda llamada JEV se registra. Antes de crear el proyecto va a un log propio
    # (gitignored bajo proyectos/); costo_generacion.py lo toma con --log.
    log = a.log or os.path.join(REPO, "proyectos", "_enrutador", "recursos", "costos.jsonl")
    try:
        res = decision.decidir({"peticion": texto}, preguntas(), REPO, log=log)
    except SystemExit as e:
        print(f"ERROR API de decisiones: {e}")
        return 4
    elegida, p1, segunda, p2 = interpretar(res)
    if elegida not in RUTAS:
        print("ERROR la respuesta de JEV no trae una opción válida; pregunta al usuario qué necesita.")
        return 4
    r = RUTAS[elegida]
    if p1 < a.umbral:
        print(f"ruta ambigua: {elegida} ({p1:.2f}) vs {segunda} ({p2:.2f})")
        print(f"Siguiente: pregunta al usuario (una sola pregunta, AGENT §2) si quiere {RUTAS[elegida]['desc'].split(',')[0].lower()} "
              f"o {RUTAS[segunda]['desc'].split(',')[0].lower() if segunda in RUTAS else 'otra cosa'}.")
        return 0
    print(f"ruta: {elegida} ({p1:.2f}) · skill: {r['skill']}")
    for i, paso in enumerate(r["pasos"], 1):
        print(f"  {i}. {paso}")
    print("Siguiente: aclaración previa (AGENT §2) y luego el paso 1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
