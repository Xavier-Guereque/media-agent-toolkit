"""Estilo de la casa para animaciones 3D en Blender: caricatura a todo color (nada de gris «sin chiste»).

Se importa desde un script de escenas que corre en Blender (`blender -b --factory-startup -P escena.py -- …`):

    sys.path.insert(0, "<repo>/scripts")
    import blender_estilo as est
    C.update(est.PALETA)                 # colores de piezas antes de crear materiales
    ...                                  # arma la escena
    est.caricatura(bpy.context.scene)    # cielo, piso, luz alegre y contorno oscuro

Decisiones (ver docs/Lecciones-2026-11-11-drywall-refuerzos-rack):
- Paleta saturada y distinta por tipo de pieza (parante azul, riel morado, madera naranja, tabla amarilla, muro coral):
  se lee qué es cada cosa sin rótulo y el cuadro nunca se ve gris.
- Contorno con **casco invertido** (Solidify con normales volteadas + material oscuro con backface culling): cuesta casi
  nada en Eevee. Freestyle hizo el cuadro varias veces más lento y se colgó (6.8 GB): no usarlo.
- Las mallas deben tener escala 1 (medidas en la malla): con escala no uniforme el contorno sale disparejo.
  `contorno()` hornea la escala de los objetos sin escala animada.
- Luz frontal de relleno: sin ella las caras que miran a cámara quedan en sombra y el cielo azul las agrisa.
- Solo el sol proyecta sombra: con 20 muestras, las sombras suaves de las luces de área grandes llenan de grano las
  superficies lisas (y un filtro antigrano en FFmpeg no lo arregla). El relleno va sin sombra y con poca energía.
- Herramientas que van encima de piezas de color (nivel, regla) llevan un color que contraste: nivel rojo sobre la
  tabla amarilla.
- Rótulos grandes: ≥ 60 px en pantalla para rótulos anclados y ≥ 66 px para títulos (a 38 px «casi no se ven»).
CC0.
"""
import math

PALETA = {
    "metal": "#3FA9F5",      # parantes / perfiles
    "riel": "#B36BFF",
    "madera": "#FF8C42",
    "tabla": "#FFC93C",
    "placa": "#FFE6B8",      # yeso: crema cálido (con emisión ≈ 0.3 para que no se agrise)
    "muro": "#FF6B8B",       # muro existente / losa
    "piso": "#5CC46A",
    "piso_linea": "#8EE59B",
    "cielo": "#7FD1FF",
    "linea": "#14112B",      # contorno
    "rack": "#2F6BFF",
    "pantalla": "#2E7BE6",
}
ROTULO_MIN_PX = 60
TITULO_MIN_PX = 66


def _lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple((x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c) + (1.0,)


def _material_linea(color):
    import bpy
    m = bpy.data.materials.get("contorno_casa") or bpy.data.materials.new("contorno_casa")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs[0].default_value = _lin(color)
    nt.links.new(em.outputs[0], nt.nodes.new("ShaderNodeOutputMaterial").inputs[0])
    m.use_backface_culling = True
    return m


def _escala_animada(o):
    ad = o.animation_data
    if not ad or not ad.action:
        return False
    try:
        curvas = list(ad.action.fcurves)
    except AttributeError:                                   # Blender 5: acciones con ranuras
        from bpy_extras import anim_utils
        cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
        curvas = list(cb.fcurves) if cb else []
    return any(fc.data_path == "scale" for fc in curvas)


def contorno(objetos=None, color=PALETA["linea"], grueso=0.006, fino=0.003, min_dim=0.015,
             excluir=("plano", "panel", "trazo", "Plane", "piso")):
    """Agrega el contorno de casco invertido a cada malla visible (no textos, HUD, transparencias ni piezas diminutas)."""
    import bpy
    from mathutils import Matrix
    linea = _material_linea(color)
    for o in list(objetos or bpy.data.objects):
        if o.type != "MESH" or o.get("sin_tinta") or o.name.startswith(excluir):
            continue
        if o.parent and o.parent.type in ("FONT", "CAMERA"):
            continue
        if not o.data.materials or o.data.materials[0] is None or o.data.materials[0].name.startswith("plano"):
            continue
        if any(md.type == "SOLIDIFY" and md.name == "contorno" for md in o.modifiers):
            continue
        if tuple(o.scale) != (1.0, 1.0, 1.0) and not _escala_animada(o) and o.data.users == 1:
            o.data.transform(Matrix.Diagonal(tuple(o.scale) + (1.0,)))
            o.scale = (1.0, 1.0, 1.0)
        d = max(o.dimensions)
        if d < min_dim:
            continue
        o.data.materials.append(linea)
        md = o.modifiers.new("contorno", "SOLIDIFY")
        md.thickness = grueso if d > 0.5 else fino
        md.offset = 1.0
        md.use_flip_normals = True
        md.use_rim = False
        md.material_offset = len(o.data.materials) - 1


def caricatura(sc, paleta=PALETA, fondo=0.55, frente=220, con_contorno=True):
    """Cielo claro, piso verde con cuadrícula (si hay material «piso» con nodo Mix), luz alegre y contorno."""
    import bpy
    w = sc.world
    if w and w.use_nodes and "Background" in w.node_tree.nodes:
        bg = w.node_tree.nodes["Background"]
        bg.inputs[0].default_value = _lin(paleta["cielo"])
        bg.inputs[1].default_value = fondo
    piso = bpy.data.materials.get("piso")
    if piso and piso.use_nodes:
        for n in piso.node_tree.nodes:
            if n.bl_idname == "ShaderNodeMix":
                n.inputs["A"].default_value = _lin(paleta["piso"])
                n.inputs["B"].default_value = _lin(paleta["piso_linea"])
    for o in bpy.data.objects:            # relleno sin sombra: las sombras suaves de áreas grandes dan grano en Eevee
        if o.type == "LIGHT":
            o.data.energy *= 1.5 if o.data.type == "SUN" else 0.45
            if o.data.type != "SUN":
                o.data.use_shadow = False
    if frente and not bpy.data.objects.get("frente_casa"):
        luz = bpy.data.lights.new("frente_casa", "AREA")
        luz.energy, luz.size = frente, 5
        luz.use_shadow = False
        o = bpy.data.objects.new("frente_casa", luz)
        cam = sc.camera
        o.location = (cam.location.x if cam else 0.0, -4.5, 2.6)
        o.rotation_euler = (math.radians(68), 0, 0)
        sc.collection.objects.link(o)
    if con_contorno:
        contorno()
