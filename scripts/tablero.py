#!/usr/bin/env python3
"""tablero — dashboard local (localhost) con el avance de los procesos largos de un proyecto.

Uso: python3 scripts/tablero.py [proyectos/<slug>_<DDMMAAAA>] [--puerto 8765]
     (sin proyecto: el más reciente de `proyectos/`). Abrir http://127.0.0.1:<puerto>/

Estándar de avance del toolkit (AGENT §9): toda etapa larga reporta con `comun.avance(etapa, pct,
detalle, datos=…)`, que escribe una línea JSON en `recursos/avance.jsonl` del proyecto activo:
  {"ts": 1761860000.1, "etapa": "voz", "pct": 45.9, "detalle": "u17 …", "estado": "en_curso",
   "datos": {"etiqueta": "u17", "valor": 3.1, "limite": 3.3, "unidad": "s"}}
El tablero lo lee cada 2 s y dibuja: anillo con el total, una barra + sparkline + ETA por etapa, una
gráfica «valor vs límite» cuando una etapa reporta `datos` (p. ej. duración de cada toma frente a su
hueco), y el registro reciente. También entiende los logs de `doblar.py` anteriores al estándar
(`recursos/doblaje/voz.log` y `render.log`) para no perder piezas en curso.
Solo librería estándar; no escribe nada en el proyecto; sin dependencias ni CDN (funciona sin red).
"""
import argparse
import glob
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROYECTO = "."
ORDEN = ["descarga", "transcripcion", "unidades", "traduccion", "voz", "render", "qa", "cortinillas", "verificacion"]
NOMBRES = {"descarga": "Descarga", "transcripcion": "Transcripción", "unidades": "Unidades", "cortinillas": "Cortinillas",
           "traduccion": "Traducción", "voz": "Voz (TTS)", "render": "Render (FFmpeg)",
           "verificacion": "Verificación", "qa": "QA (stills)", "cuadros": "Cuadros", "mezcla": "Mezcla"}
_hist_legacy = {}   # etapa → [[ts, pct], …] para los logs sin estándar


def leer_lineas(ruta):
    try:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


def etapas_estandar(rec):
    """recursos/avance.jsonl → {etapa: {...}} con historial e ítems."""
    out = {}
    for ln in leer_lineas(os.path.join(rec, "avance.jsonl")):
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        et = e.get("etapa") or "etapa"
        d = out.setdefault(et, {"id": et, "pct": None, "detalle": "", "estado": "en_curso", "inicio": e.get("ts"),
                                "fin": None, "historial": [], "items": [], "unidad": None, "avisos": 0})
        pct = e.get("pct")
        if pct is not None and d["pct"] is not None and float(pct) < d["pct"] - 1e-6:
            # la etapa volvió a empezar (otra corrida): reiniciar su estado
            d.update({"inicio": e.get("ts"), "fin": None, "historial": [], "items": [], "avisos": 0, "detalle": ""})
        if pct is not None:
            d["pct"] = float(pct)
            d["historial"].append([e.get("ts"), float(pct)])
        if e.get("detalle"):
            d["detalle"] = e["detalle"]
        if e.get("estado"):
            d["estado"] = e["estado"]
        if d["estado"] == "listo" or (pct is not None and float(pct) >= 100):
            d["fin"] = e.get("ts")
        if d["estado"] == "aviso":
            d["avisos"] += 1
        datos = e.get("datos") or {}
        if "etiqueta" in datos and "valor" in datos:
            d["items"] = [it for it in d["items"] if it["etiqueta"] != datos["etiqueta"]]
            d["items"].append({"etiqueta": datos["etiqueta"], "valor": datos["valor"],
                               "limite": datos.get("limite"), "nota": datos.get("nota")})
            d["unidad"] = datos.get("unidad") or d["unidad"]
    return out


def nacimiento(ruta):
    """Hora de creación del archivo (st_birthtime en macOS; ctime cambia con cada escritura)."""
    st = os.stat(ruta)
    return getattr(st, "st_birthtime", None) or st.st_ctime


def muestra_legacy(et, pct):
    h = _hist_legacy.setdefault(et, [])
    if not h or abs(h[-1][1] - pct) > 0.01:
        h.append([time.time(), pct])
    return h[-120:]


def etapas_legacy(rec, ya):
    """voz.log / render.log de doblar.py (versiones sin comun.avance)."""
    out = {}
    spec = os.path.join(PROYECTO, "doblaje.json")
    total_u = None
    if os.path.exists(spec):
        try:
            total_u = len(json.load(open(spec, encoding="utf-8")).get("unidades") or [])
        except (OSError, json.JSONDecodeError):
            pass
    voz = os.path.join(rec, "doblaje", "voz.log")
    if "voz" not in ya and os.path.exists(voz):
        lineas = leer_lineas(voz)
        items, avisos = [], 0
        for ln in lineas:
            m = re.search(r"(u\d+) natural ([\d.]+)s → ([\d.]+)s / slot ([\d.]+)s\s+atempo ([\d.]+)", ln)
            if m:
                items.append({"etiqueta": m.group(1), "valor": float(m.group(3)), "limite": float(m.group(4)),
                              "nota": f"atempo {m.group(5)}" if float(m.group(5)) > 1.0 else None})
            if "W-DOBLAJE-LARGO" in ln:
                avisos += 1
        listo = any("Pista de voz" in ln for ln in lineas)
        pct = 100.0 if listo else (100.0 * len(items) / total_u if total_u else None)
        out["voz"] = {"id": "voz", "pct": pct, "estado": "listo" if listo else "en_curso",
                      "detalle": "pista de voz ensamblada" if listo else (items[-1]["etiqueta"] + " sintetizada" if items else "arrancando…"),
                      "inicio": nacimiento(voz),
                      "fin": os.path.getmtime(voz) if listo else None, "historial": muestra_legacy("voz", pct or 0.0),
                      "items": items, "unidad": "s", "avisos": avisos}
    render = os.path.join(rec, "doblaje", "render.log")
    if "render" not in ya and os.path.exists(render):
        lineas = leer_lineas(render)
        ult = None
        for ln in lineas:
            m = re.search(r"avance\s+([\d.]+)%", ln)
            if m:
                ult = float(m.group(1))
        listo = any(ln.startswith("Salida:") for ln in lineas)
        pct = 100.0 if listo else (ult or 0.0)
        out["render"] = {"id": "render", "pct": pct, "estado": "listo" if listo else "en_curso",
                         "detalle": "mp4 terminado" if listo else (lineas[-1].strip() if lineas else "arrancando…"),
                         "inicio": nacimiento(render), "fin": os.path.getmtime(render) if listo else None,
                         "historial": muestra_legacy("render", pct), "items": [], "unidad": None, "avisos": 0}
    return out


def eta(hist, pct):
    """Segundos restantes por la pendiente de los últimos ~3 min de historial; None si no hay base."""
    if pct is None or pct >= 100 or len(hist) < 2:
        return None
    ahora = hist[-1][0]
    base = [h for h in hist if h[0] and ahora - h[0] <= 180]
    if len(base) < 2 or base[-1][1] <= base[0][1] or base[-1][0] <= base[0][0]:
        return None
    tasa = (base[-1][1] - base[0][1]) / (base[-1][0] - base[0][0])
    return (100 - pct) / tasa if tasa > 0 else None


def estado():
    rec = os.path.join(PROYECTO, "recursos")
    etapas = etapas_estandar(rec)
    etapas.update(etapas_legacy(rec, etapas))
    orden = [e for e in ORDEN if e in etapas] + sorted(e for e in etapas if e not in ORDEN)
    lista = []
    for e in orden:
        d = dict(etapas[e])
        d["nombre"] = NOMBRES.get(e, e.replace("_", " ").capitalize())
        d["eta"] = eta(d["historial"], d["pct"])
        d["historial"] = d["historial"][-120:]
        lista.append(d)
    con = [d for d in lista if d["pct"] is not None]
    total = sum(d["pct"] for d in con) / len(lista) if lista and con else None
    terminado = bool(lista) and all(d["estado"] == "listo" for d in lista)
    inicio = min((d["inicio"] for d in lista if d.get("inicio")), default=None)
    registro = []
    for ln in leer_lineas(os.path.join(rec, "avance.jsonl"))[-12:]:
        try:
            e = json.loads(ln)
            registro.append(f"{time.strftime('%H:%M:%S', time.localtime(e.get('ts') or 0))}  {e.get('etapa', ''):<13} {str(e.get('pct') if e.get('pct') is not None else ''):>5}  {e.get('detalle', '')}")
        except json.JSONDecodeError:
            pass
    if not registro:
        for nombre in ("doblaje/render.log", "doblaje/voz.log"):
            ln = leer_lineas(os.path.join(rec, nombre))[-6:]
            if ln:
                registro = [f"{nombre.split('/')[-1]}  {x.strip()}" for x in ln]
                break
    return {"proyecto": os.path.basename(os.path.abspath(PROYECTO)), "ahora": time.time(), "inicio": inicio,
            "total_pct": total, "terminado": terminado, "etapas": lista, "registro": registro}


PAGINA = r"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Tablero</title>
<style>
:root{color-scheme:light;--bg:#f4f3ef;--surface:#fcfcfb;--line:#e6e4df;--text:#0b0b0b;--text-2:#52514e;--muted:#8a8985;
 --serie:#2a78d6;--pista:#cde2fb;--bien:#0ca30c;--aviso:#fab219;--grave:#ec835a;--critico:#d03b3b;--sombra:0 1px 2px rgba(0,0,0,.05)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#121211;--surface:#1a1a19;--line:#2c2b29;--text:#f0efec;--text-2:#c3c2b7;--muted:#8f8e88;--serie:#3987e5;--pista:#184f95;--sombra:none}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#121211;--surface:#1a1a19;--line:#2c2b29;--text:#f0efec;--text-2:#c3c2b7;--muted:#8f8e88;--serie:#3987e5;--pista:#184f95;--sombra:none}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--text);font:14px/1.4 -apple-system,"Helvetica Neue",Segoe UI,Roboto,sans-serif}
main{max-width:1040px;margin:0 auto;padding:18px 16px 28px}
.cab{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:12px}
.kicker{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
h1{font-size:19px;font-weight:600;margin:2px 0 4px}.meta{color:var(--text-2);font-size:13px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;padding:1px 9px;font-size:12px;color:var(--text-2);background:var(--surface);white-space:nowrap}
.chip i{width:7px;height:7px;border-radius:50%;background:var(--muted);display:inline-block}
.chip.run i{background:var(--serie);animation:pulso 2s ease-in-out infinite}.chip.ok i{background:var(--bien)}.chip.warn i{background:var(--aviso)}.chip.err i{background:var(--critico)}
@keyframes pulso{0%,100%{opacity:1}50%{opacity:.35}}
.anillo{position:relative;width:88px;height:88px;flex:none}.anillo svg{width:88px;height:88px;transform:rotate(-90deg)}
.anillo .pista{stroke:var(--pista)}.anillo .valor{stroke:var(--serie);transition:stroke-dashoffset .8s ease}.anillo.ok .valor{stroke:var(--bien)}
.anillo b{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:600}
.tarjeta{background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:var(--sombra);padding:10px 14px 12px;margin-bottom:10px}
.tarjeta h2{font-size:12px;font-weight:600;color:var(--text-2);letter-spacing:.03em;text-transform:uppercase;margin:0 0 8px;display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.tarjeta h2 .sub{font-weight:400;text-transform:none;letter-spacing:0;color:var(--muted)}
.etapas{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:8px}
.etapa{border:1px solid var(--line);border-radius:10px;padding:9px 11px 10px}.etapa.pend{opacity:.6}
.etapa .cab2{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px}.etapa .nom{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.barra{height:8px;border-radius:4px;background:var(--pista);overflow:hidden}.barra div{height:100%;border-radius:4px 2px 2px 4px;background:var(--serie);width:0;transition:width .7s ease}
.etapa.ok .barra div{background:var(--bien)}
.fila{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:12px;color:var(--text-2);margin-top:5px}.fila b{color:var(--text);font-variant-numeric:tabular-nums;font-size:13px}
.fila svg{width:84px;height:22px;flex:none}.fila path{fill:none;stroke:var(--serie);stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.fila circle{fill:var(--serie);stroke:var(--surface);stroke-width:2}
.det{font-size:12px;color:var(--muted);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tiles{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:0 0 8px}
.tile{border:1px solid var(--line);border-radius:8px;padding:6px 10px}.tile .l{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.tile .v{font-size:18px;font-weight:600;margin-top:1px}
.graf{position:relative}.graf svg{width:100%;height:150px;display:block}.graf .eje{stroke:var(--line);stroke-width:1}.graf text{fill:var(--muted);font-size:10px;font-variant-numeric:tabular-nums}
.graf rect.b{fill:var(--serie);transition:height .6s ease,y .6s ease}.graf rect.b.sobre{fill:var(--aviso)}.graf rect.hit{fill:transparent;cursor:default}.graf rect.hit:hover + rect.b,.graf rect.hit:focus + rect.b{opacity:.75}
.graf .ref{stroke:var(--text-2);stroke-width:1}.graf .refl{fill:var(--text-2);font-size:10px}
.tip{position:absolute;pointer-events:none;background:var(--text);color:var(--bg);font-size:12px;padding:5px 8px;border-radius:6px;transform:translate(-50%,-110%);white-space:nowrap;opacity:0;transition:opacity .15s}.tip b{font-size:13px}
.leyenda{display:inline-flex;gap:12px;font-size:11px;color:var(--text-2);font-weight:400;text-transform:none;letter-spacing:0}.leyenda i{display:inline-block;width:10px;height:10px;border-radius:3px;background:var(--serie);vertical-align:-1px;margin-right:5px}.leyenda i.a{background:var(--aviso)}
details{font-size:12px;color:var(--text-2)}summary{cursor:pointer;color:var(--muted)}table{border-collapse:collapse;width:100%;margin-top:6px;font-variant-numeric:tabular-nums}td,th{text-align:right;padding:3px 8px;border-top:1px solid var(--line)}td:first-child,th:first-child{text-align:left}
pre{font:11.5px/1.45 ui-monospace,Menlo,monospace;color:var(--text-2);margin:6px 0 0;white-space:pre-wrap;word-break:break-word}
.vacio{color:var(--muted);padding:8px 0}
@media (max-width:640px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style></head><body><main>
<header class="cab"><div><div class="kicker">Tablero · media-agent-toolkit</div><h1 id="titulo">…</h1>
<div class="meta"><span class="chip" id="chip"><i></i><span>conectando</span></span><span id="tiempo"></span><span id="hora"></span></div></div>
<div class="anillo" id="anillo"><svg viewBox="0 0 88 88"><circle class="pista" cx="44" cy="44" r="38" fill="none" stroke-width="8"/><circle class="valor" cx="44" cy="44" r="38" fill="none" stroke-width="8" stroke-linecap="round" stroke-dasharray="238.8" stroke-dashoffset="238.8"/></svg><b id="total">—</b></div></header>
<section class="tarjeta"><h2>Etapas</h2><div id="etapas" class="vacio">Esperando el primer reporte de avance…</div></section>
<section class="tarjeta" id="secAjuste" hidden><h2><span>Ajuste de cada toma a su hueco <span class="sub" id="sAjuste"></span></span><span class="leyenda"><span><i></i>cabe</span><span><i class="a"></i>se pasa ▲</span></span></h2>
<div class="tiles" id="tiles"></div>
<div class="graf"><svg id="graf" viewBox="0 0 920 150" preserveAspectRatio="none"></svg><div class="tip" id="tip"></div></div>
<details><summary>Ver tabla</summary><table id="tabla"></table></details></section>
<section class="tarjeta"><details id="detReg"><summary id="sumReg">Registro</summary><pre id="registro">—</pre></details></section>
</main>
<script>
const $=id=>document.getElementById(id);const fmtT=s=>{if(s==null)return'';s=Math.max(0,Math.round(s));return s<60?s+' s':Math.floor(s/60)+' min '+String(s%60).padStart(2,'0')+' s'};
let totalMostrado=0,raf=null;
function tween(a,b){cancelAnimationFrame(raf);const t0=performance.now();const d=700;const paso=t=>{const k=Math.min(1,(t-t0)/d);const v=a+(b-a)*(1-Math.pow(1-k,3));$('total').textContent=v.toFixed(v>=99.95?0:1)+'%';if(k<1)raf=requestAnimationFrame(paso)};raf=requestAnimationFrame(paso)}
function spark(h){if(!h||h.length<2)return'';const xs=h.map(p=>p[0]),ys=h.map(p=>p[1]);const x0=Math.min(...xs),x1=Math.max(...xs)||x0+1;const W=84,H=22;
 const pts=h.map(p=>[(p[0]-x0)/(x1-x0||1)*(W-6)+3,H-3-(p[1]/100)*(H-6)]);const d=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');const u=pts[pts.length-1];
 return`<svg viewBox="0 0 ${W} ${H}"><path d="${d}"/><circle cx="${u[0].toFixed(1)}" cy="${u[1].toFixed(1)}" r="3.5"/></svg>`}
function clase(e){return e.estado==='listo'?'ok':e.estado==='error'?'err':e.estado==='aviso'?'warn':e.pct==null?'pend':'run'}
function etiqueta(e){return{ok:'listo',err:'error',warn:'con avisos',pend:'pendiente',run:'en curso'}[clase(e)]}
function pintar(j){$('titulo').textContent=j.proyecto;const c=$('chip');const cl=j.terminado?'ok':(j.etapas.some(e=>e.estado==='error')?'err':'run');c.className='chip '+cl;c.lastElementChild.textContent=j.terminado?'terminado':cl==='err'?'con error':'en curso';
 $('tiempo').textContent=j.inicio?'· '+fmtT(j.ahora-j.inicio)+' desde el inicio':'';$('hora').textContent='· '+new Date().toLocaleTimeString();
 const tot=j.total_pct==null?0:j.total_pct;$('anillo').className='anillo'+(j.terminado?' ok':'');$('anillo').querySelector('.valor').style.strokeDashoffset=(238.8*(1-tot/100)).toFixed(1);if(Math.abs(tot-totalMostrado)>0.05){tween(totalMostrado,tot);totalMostrado=tot}
 const cont=$('etapas');if(!j.etapas.length){cont.className='vacio';cont.textContent='Esperando el primer reporte de avance…'}else{cont.className='etapas';cont.innerHTML='';
  for(const e of j.etapas){const k=clase(e);const div=document.createElement('div');div.className='etapa '+k;
   div.innerHTML=`<div class="cab2"><span class="nom"></span><span class="chip ${k}"><i></i><span></span></span></div><div class="barra"><div></div></div><div class="fila"><span class="dur"></span><span class="sp"></span><b class="pct"></b></div><div class="det"></div>`;
   div.querySelector('.nom').textContent=e.nombre;div.querySelector('.chip span').textContent=etiqueta(e)+(e.avisos?` · ${e.avisos} aviso${e.avisos>1?'s':''}`:'');
   div.querySelector('.pct').textContent=e.pct==null?'—':e.pct.toFixed(1)+'%';div.querySelector('.barra div').style.width=(e.pct||0)+'%';
   const dur=e.inicio?(e.fin?'duró '+fmtT(e.fin-e.inicio):fmtT(j.ahora-e.inicio)+(e.eta!=null?' · ~'+fmtT(e.eta)+' restantes':'')):'';div.querySelector('.dur').textContent=dur;div.querySelector('.sp').innerHTML=spark(e.historial);div.querySelector('.det').textContent=e.detalle||'';cont.appendChild(div)}}
 const con=j.etapas.find(e=>e.items&&e.items.length);$('secAjuste').hidden=!con;if(con)grafica(con);
 $('registro').textContent=j.registro.length?j.registro.join('\n'):'—';$('sumReg').textContent='Registro'+(j.registro.length?' · '+j.registro[j.registro.length-1].replace(/\s+/g,' ').slice(0,90):'')}
function grafica(e){const it=e.items,u=e.unidad||'';const n=it.length;const W=920,H=150,ml=40,mr=10,mt=14,mb=22;const w=W-ml-mr,h=H-mt-mb;
 const pct=it.map(x=>x.limite?x.valor/x.limite*100:null);const ymax=Math.max(120,...pct.filter(v=>v!=null))*1.05;const y=v=>mt+h-(v/ymax)*h;
 const slot=w/n,bw=Math.min(24,Math.max(3,slot-2));let s='';for(const t of [0,50,100]){s+=`<line class="eje" x1="${ml}" x2="${W-mr}" y1="${y(t)}" y2="${y(t)}"/><text x="${ml-5}" y="${y(t)+3.5}" text-anchor="end">${t}%</text>`}
 s+=`<line class="ref" x1="${ml}" x2="${W-mr}" y1="${y(100)}" y2="${y(100)}"/><text class="refl" x="${W-mr}" y="${y(100)-4}" text-anchor="end">hueco (100 %)</text>`;
 it.forEach((x,i)=>{const p=pct[i];if(p==null)return;const cx=ml+slot*i+slot/2;const top=y(p),bh=mt+h-top;const sobre=p>102;
  s+=`<rect class="hit" x="${(cx-slot/2).toFixed(1)}" y="${mt}" width="${slot.toFixed(1)}" height="${h}" tabindex="0" data-i="${i}"/><rect class="b${sobre?' sobre':''}" x="${(cx-bw/2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0,bh).toFixed(1)}" rx="0"/>`;
  if(sobre)s+=`<text x="${cx}" y="${top-4}" text-anchor="middle">▲</text>`;if(n<=40||i%Math.ceil(n/40)===0)s+=`<text x="${cx}" y="${H-7}" text-anchor="middle">${x.etiqueta}</text>`});
 $('graf').innerHTML=s;const sobre=it.filter((x,i)=>pct[i]!=null&&pct[i]>102);const med=pct.filter(v=>v!=null);const prom=med.length?med.reduce((a,b)=>a+b,0)/med.length:0;const exc=Math.max(0,...it.map(x=>x.limite?x.valor-x.limite:0));const ajust=it.filter(x=>x.nota).length;
 $('tiles').innerHTML=[['Tomas',n],['Ajuste medio',prom.toFixed(1)+'%'],['Máximo exceso',exc.toFixed(2)+' '+u],['Velocidad ajustada',ajust],['Se pasan >2 %',sobre.length]].map(([l,v])=>`<div class="tile"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('');
 $('sAjuste').textContent=sobre.length?'· se pasan: '+sobre.map(x=>x.etiqueta).join(', '):'· todas caben';
 const tb=$('tabla');tb.innerHTML='<tr><th>toma</th><th>final ('+u+')</th><th>hueco ('+u+')</th><th>ajuste</th><th>nota</th></tr>';for(const [i,x] of it.entries()){const tr=document.createElement('tr');[x.etiqueta,x.valor.toFixed(2),x.limite!=null?x.limite.toFixed(2):'—',pct[i]!=null?pct[i].toFixed(0)+'%':'—',x.nota||''].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.appendChild(td)});tb.appendChild(tr)}
 const tip=$('tip'),g=$('graf');const mostrar=r=>{const x=it[+r.dataset.i],p=pct[+r.dataset.i];tip.innerHTML='';const b=document.createElement('b');b.textContent=x.valor.toFixed(2)+' '+u+' / '+(x.limite!=null?x.limite.toFixed(2)+' '+u:'—');tip.appendChild(b);tip.appendChild(document.createTextNode(' · '+x.etiqueta+' · '+(p!=null?p.toFixed(0)+'%':'')+(x.nota?' · '+x.nota:'')));
  const bb=r.getBoundingClientRect(),gb=g.getBoundingClientRect();tip.style.left=(bb.left-gb.left+bb.width/2)+'px';tip.style.top=(bb.top-gb.top+8)+'px';tip.style.opacity=1};
 g.querySelectorAll('rect.hit').forEach(r=>{r.addEventListener('pointerenter',()=>mostrar(r));r.addEventListener('focus',()=>mostrar(r));r.addEventListener('pointerleave',()=>tip.style.opacity=0);r.addEventListener('blur',()=>tip.style.opacity=0)})}
async function tick(){try{const r=await fetch('/api/estado?t='+Date.now());pintar(await r.json())}catch(e){const c=$('chip');c.className='chip err';c.lastElementChild.textContent='sin conexión'}}
tick();setInterval(tick,2000);
</script></body></html>"""


class Manejador(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/estado"):
            cuerpo = json.dumps(estado(), ensure_ascii=False).encode()
            tipo = "application/json; charset=utf-8"
        else:
            cuerpo = PAGINA.encode()
            tipo = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *a):
        pass


def proyecto_reciente():
    """Carpeta <slug>_<DDMMAAAA> más reciente de proyectos/ (excluye _enrutador y otras carpetas auxiliares)."""
    cands = [d for d in glob.glob(os.path.join(REPO, "proyectos", "*_*"))
             if os.path.isdir(d) and re.search(r"^[^_].*_\d{8}$", os.path.basename(d))]
    if not cands:
        raise SystemExit("No hay proyectos en proyectos/ (pasa la ruta de uno).")
    return max(cands, key=os.path.getmtime)


def main():
    global PROYECTO
    p = argparse.ArgumentParser(description="Tablero local de avance de un proyecto del toolkit")
    p.add_argument("proyecto", nargs="?")
    p.add_argument("--puerto", type=int, default=8765)
    a = p.parse_args()
    PROYECTO = os.path.abspath(a.proyecto) if a.proyecto else proyecto_reciente()
    srv = ThreadingHTTPServer(("127.0.0.1", a.puerto), Manejador)
    print(f"Tablero de {os.path.basename(PROYECTO)} en http://127.0.0.1:{a.puerto}/  (Ctrl-C para parar)", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
