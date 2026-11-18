"""Popovers for the HTML output: point at a symbol in the formula and a small card opens under it.

The card says how the symbol is read and what it means. When the formula can
be worked out, it also draws the one picture that fits any formula: the result
as this symbol alone runs across its range, with a dot that travels the curve
and a line of numbers that follows it. Nothing here is written for one
formula. A formula that cannot be worked out as written (a derivative, a sum,
an operator) still gets the words, and gets the picture when ``expr`` gives a
case of it.

``cards`` makes the data, one item per ledger row. ``STYLE`` and ``SCRIPT`` go
in the fragment once and serve every eqlens figure on the page.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence

from eqlens.engine import FormulaError
from eqlens.legend import Symbol, _shape, plain

__all__ = ["SCRIPT", "STYLE", "cards", "embed"]

STEPS = 48
_LONG = 8


def _round(x: float) -> float | None:
    """A number short enough to ship, or None where the formula has no real value."""
    if x is None or math.isnan(x) or math.isinf(x):
        return None
    return float(f"{x:.5g}")


def cards(
    tex: str,
    rows: Sequence[Symbol],
    *,
    define: Sequence[str] = (),
    tier: Sequence[str] = (),
    constant: Sequence[str] = (),
    shared: Sequence[str] = (),
    sets: Sequence = (),
    expr: str | None = None,
    solve: str | None = None,
    plot: bool = True,
) -> list[dict]:
    """One card per row, in row order: ``g`` the symbol, ``t`` its title, ``n`` its note, ``c`` its color.

    A symbol the formula can be worked out for also has ``lo``, ``hi``, ``at``
    (its range and where it stands), ``ys`` (the result across the range,
    None where there is none), ``st`` (its step, when it moves in steps), ``out`` (what the result is called), and the
    units ``u`` and ``ou``. A constant has ``v``, its value. What the formula
    gives has ``now``, the result where every symbol stands. ``plot`` False
    keeps the words and leaves the numbers out: for a formula of matrices or
    tensors, which reads as arithmetic but is not a curve.
    """
    found = []
    for row in rows:
        glyph = plain(f"${row.key}$")
        name = plain(row.name) if row.name else ""
        if len(glyph) > _LONG or "frac" in glyph or "sqrt" in glyph:
            # A whole power or fraction as one row: its plain text reads badly, and its parts have cards of their own.
            found.append({"g": "", "t": "", "n": plain(row.hint) if row.defined else "", "c": row.color or ""})
            continue
        found.append({"g": glyph, "t": name if name and name != glyph else "", "n": plain(row.hint), "c": row.color or ""})

    if not plot:
        return found
    # Imported here: the bench imports the renderer, and the renderer imports this.
    from eqlens.bench.spec import build, curve, work_out

    try:
        spec = build(tex, expr=expr, solve=solve, sets=sets, define=define, tier=tier, constant=constant, shared=shared)
    except FormulaError:
        if expr or solve or sets:
            raise
        return found

    where: dict[tuple, int] = {}
    for index, row in enumerate(rows):
        where.setdefault(_shape(row.key), index)
    output = spec["output"]
    for entry in spec["symbols"]:
        index = where.get(_shape(entry["key"]))
        if index is None:
            continue
        card = found[index]
        card["u"] = entry["unit"]
        if entry["role"] == "constant":
            card["v"] = entry["value"]
            continue
        _xs, ys = curve(spec, entry["key"], STEPS)
        ys = [_round(y) for y in ys]
        if all(y is None for y in ys):
            continue
        card.update(lo=entry["min"], hi=entry["max"], at=entry["value"], ys=ys, out=output["shown"], ou=output["unit"])
        if entry.get("step"):
            # It moves in steps: the card draws a dot for each and no line between.
            card["st"] = entry["step"]
    if output["key"]:
        index = where.get(_shape(output["key"]))
        now = _round(work_out(spec))
        if index is not None and now is not None and "ys" not in found[index]:
            found[index].update(now=now, u=output["unit"])
    return found


def embed(found: Sequence[dict]) -> str:
    """The cards as a block of JSON for the fragment. Empty when no card has anything to say."""
    if not any(card["t"] or card["n"] or "ys" in card or "v" in card or "now" in card for card in found):
        return ""
    data = json.dumps(list(found), ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f'<script type="application/json" class="eqlens-pops">{data}</script>'


STYLE = (
    ".eqlens{position:relative}"
    ".eqlens-hint{margin-right:auto;align-self:center;font:500 12px/1 system-ui,sans-serif;color:var(--eq-dim,#8b949e);"
    "transition:opacity .2s ease}"
    ".eqlens.seen .eqlens-hint{opacity:0}"
    ".eqlens-hint .t{display:none}"
    "@media (hover:none){.eqlens-hint .h{display:none}.eqlens-hint .t{display:inline}}"
    ".eqlens svg g.f.h{cursor:pointer}"
    ".eqlens svg g.f.h:focus{outline:none}"
    ".eqlens svg g.f.h:focus-visible .hit{stroke:var(--eq-fg,#f2f2f7);stroke-width:1;stroke-dasharray:2 2}"
    ".eqlens svg.eqlens-lit :is(.f,.r){opacity:.28}"
    ".eqlens svg.eqlens-lit .eqlens-on{opacity:1}"
    ".eqlens-pop{position:absolute;z-index:20;box-sizing:border-box;width:min(300px,100vw - 16px);padding:13px 15px 12px;"
    "text-align:left;background:var(--eq-pop-bg,#1c1f27);color:var(--eq-fg,#f2f2f7);"
    "border:1px solid var(--eq-pop-line,#343a46);border-radius:14px;box-shadow:0 16px 44px rgba(0,0,0,.45);"
    "font:14px/1.4 system-ui,sans-serif;opacity:0;visibility:hidden;pointer-events:none;transform:translateY(6px);"
    "transition:opacity .18s ease,transform .18s ease,visibility 0s .18s}"
    ".eqlens-pop.open{opacity:1;visibility:visible;transform:none;transition:opacity .18s ease,transform .18s ease}"
    ".eqlens-pop::before{content:'';position:absolute;left:var(--nx,50%);top:-7px;width:12px;height:12px;margin-left:-6px;"
    "background:var(--eq-pop-bg,#1c1f27);border-left:1px solid var(--eq-pop-line,#343a46);"
    "border-top:1px solid var(--eq-pop-line,#343a46);transform:rotate(45deg)}"
    ".eqlens-pop p{margin:0}"
    ".eqlens-pop-title{font-weight:600;font-size:15px}"
    ".eqlens-pop-title b{font-size:17px;margin-right:7px}"
    ".eqlens-pop svg{display:block;width:100%;height:auto;max-width:none;margin:9px 0 5px;overflow:visible}"
    ".eqlens-pop svg text{font:10px system-ui,sans-serif;fill:var(--eq-dim,#8b949e)}"
    ".eqlens-pop-read{font-variant-numeric:tabular-nums;font-size:13px}"
    ".eqlens-pop-note{color:var(--eq-dim,#aab1bb);margin-top:6px!important}"
    "@media (prefers-reduced-motion:reduce){.eqlens-pop{transition:none}}"
)

# One set of listeners for every eqlens figure on the page. A later fragment calls the first one's setup again.
SCRIPT = r"""(function(){
if(window.__eqlensPop){window.__eqlensPop();return}
var NS='http://www.w3.org/2000/svg',W=300,H=104,L=4,R=4,T=8,B=20;
var cur=null,pinned=false,raf=0,still=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
function cards(f){if(!f.__pops){var s=f.querySelector('script.eqlens-pops');
 try{f.__pops=JSON.parse(s.textContent)}catch(e){f.__pops=[]}}return f.__pops}
function full(c){return c&&(c.t||c.n||c.ys||c.v!=null||c.now!=null)}
function pick(g,f){var d=cards(f),best=-1;g.classList.forEach(function(k){var m=/^s(\d+)$/.exec(k);if(!m)return;
 var i=+m[1];if(!full(d[i]))return;if(best<0||(d[i].ys&&!d[best].ys))best=i});return best}
function num(x){if(x==null||!isFinite(x))return 'no real value';var a=Math.abs(x);
 return (a!==0&&(a>=1e5||a<1e-3))?x.toExponential(2).replace(/\.?0+e/,'e').replace('e+','e'):String(+x.toPrecision(3))}
function unit(u){return u?' '+u:''}
function span(ys){var all=ys.filter(function(y){return y!=null}).sort(function(a,b){return a-b});
 var lo=all[0],hi=all[all.length-1],p=function(q){return all[Math.min(all.length-1,Math.floor(q*all.length))]};
 var a=p(.03),b=p(.97);if(b>a&&(hi-lo)>40*(b-a)){lo=a-(b-a);hi=b+(b-a)}
 if(hi===lo){hi+=Math.abs(hi)||1;lo-=Math.abs(lo)||1}return [lo,hi]}
function el(n,a,t){var e=document.createElementNS(NS,n);for(var k in a)e.setAttribute(k,a[k]);if(t!=null)e.textContent=t;return e}
function box(f){var p=f.querySelector('.eqlens-pop');if(p)return p;p=document.createElement('div');
 p.className='eqlens-pop';p.setAttribute('role','tooltip');
 p.innerHTML='<p class="eqlens-pop-title"><b></b><span></span></p>\x3csvg viewBox="0 0 '+W+' '+H+'" aria-hidden="true"></svg>'+
  '<p class="eqlens-pop-read"></p><p class="eqlens-pop-note"></p>';f.appendChild(p);return p}
function plot(p,c){var svg=p.querySelector('svg'),read=p.querySelector('.eqlens-pop-read');
 cancelAnimationFrame(raf);svg.textContent='';
 if(!c.ys){svg.style.display='none';
  read.textContent=c.v!=null?c.g+' = '+num(c.v)+unit(c.u):c.now!=null?c.g+' = '+num(c.now)+unit(c.u)+' as it stands':'';
  read.style.display=read.textContent?'':'none';return}
 svg.style.display='';read.style.display='';
 var ys=c.ys,n=ys.length-1,s=span(ys),lo=s[0],hi=s[1],ink=c.c||'currentColor';
 function X(u){return L+u*(W-L-R)}
 function Y(y){return T+(1-(Math.max(lo,Math.min(hi,y))-lo)/(hi-lo))*(H-T-B)}
 if(lo<0&&hi>0)svg.appendChild(el('line',{x1:L,x2:W-R,y1:Y(0),y2:Y(0),stroke:'currentColor','stroke-opacity':.22,'stroke-dasharray':'3 3'}));
 svg.appendChild(el('line',{x1:L,x2:W-R,y1:H-B+4,y2:H-B+4,stroke:'currentColor','stroke-opacity':.22}));
 var d='',pen=false;ys.forEach(function(y,i){if(y==null){pen=false;return}d+=(pen?'L':'M')+X(i/n).toFixed(1)+' '+Y(y).toFixed(1);pen=true});
 if(c.st){ys.forEach(function(y,i){if(y==null)return;var x=X(i/n).toFixed(1);
   svg.appendChild(el('line',{x1:x,x2:x,y1:H-B+4,y2:Y(y).toFixed(1),stroke:ink,'stroke-opacity':.3}));
   svg.appendChild(el('circle',{cx:x,cy:Y(y).toFixed(1),r:n>40?1.6:2.6,fill:ink}))})}
 else svg.appendChild(el('path',{d:d,fill:'none',stroke:ink,'stroke-width':2.2,'stroke-linejoin':'round','stroke-linecap':'round'}));
 svg.appendChild(el('text',{x:L,y:H-4},num(c.lo)));
 svg.appendChild(el('text',{x:W-R,y:H-4,'text-anchor':'end'},num(c.hi)));
 svg.appendChild(el('text',{x:W/2,y:H-4,'text-anchor':'middle'},c.g+unit(c.u)));
 var hair=el('line',{y1:T,y2:H-B+4,stroke:ink,'stroke-opacity':.45}),dot=el('circle',{r:4.5,fill:ink,stroke:'var(--eq-pop-bg,#1c1f27)','stroke-width':2});
 svg.appendChild(hair);svg.appendChild(dot);
 function put(u){if(c.st)u=Math.round(u*n)/n;var q=u*n,i=Math.min(n-1,Math.floor(q)),a=ys[i],b=ys[i+1],y=(a==null||b==null)?null:a+(b-a)*(q-i),x=c.lo+(c.hi-c.lo)*u;
  hair.setAttribute('x1',X(u));hair.setAttribute('x2',X(u));
  if(y==null){dot.style.display='none'}else{dot.style.display='';dot.setAttribute('cx',X(u));dot.setAttribute('cy',Y(y))}
  read.textContent=c.g+' = '+num(x)+unit(c.u)+'  →  '+c.out+' = '+num(y)+(y==null?'':unit(c.ou))}
 var home=(c.hi>c.lo)?Math.max(0,Math.min(1,(c.at-c.lo)/(c.hi-c.lo))):.5;
 if(still){put(home);return}
 // Start where the symbol stands, then travel the range and back.
 var t0=performance.now(),ph=Math.acos(1-2*home);
 (function step(now){put(.5-.5*Math.cos(ph+(now-t0)/(c.st?Math.max(5200,n*900):5200)*2*Math.PI));raf=requestAnimationFrame(step)})(t0)}
function light(f,i){f.querySelectorAll('svg').forEach(function(s){if(!s.closest('.eqlens-pop'))s.classList.toggle('eqlens-lit',i>=0)});
 f.querySelectorAll('.eqlens-on').forEach(function(e){e.classList.remove('eqlens-on')});
 if(i>=0)f.querySelectorAll('g.s'+i).forEach(function(e){e.classList.add('eqlens-on')})}
function show(g){var f=g.closest('.eqlens');if(!f)return;var i=pick(g,f);if(i<0)return;
 var c=cards(f)[i],p=box(f);if(cur&&cur.f!==f)hide();
 if(!cur||cur.i!==i||cur.f!==f){p.querySelector('b').textContent=c.g;p.querySelector('b').style.color=c.c||'';
  p.querySelector('span').textContent=c.t;var note=p.querySelector('.eqlens-pop-note');note.textContent=c.n;
  note.style.display=c.n?'':'none';plot(p,c)}
 cur={f:f,i:i,g:g};light(f,i);
 var gb=g.getBoundingClientRect(),fb=f.getBoundingClientRect(),pw=p.offsetWidth,vw=document.documentElement.clientWidth;
 var mid=gb.left+gb.width/2,left=Math.max(8,Math.min(mid-pw/2,vw-pw-8));
 p.style.left=(left-fb.left)+'px';p.style.top=(gb.bottom-fb.top+12)+'px';
 p.style.setProperty('--nx',Math.max(20,Math.min(pw-20,mid-left))+'px');
 p.classList.add('open');f.classList.add('seen')}
function hide(){if(!cur)return;cancelAnimationFrame(raf);var p=cur.f.querySelector('.eqlens-pop');if(p)p.classList.remove('open');
 light(cur.f,-1);cur=null;pinned=false}
function term(t){return t&&t.closest?t.closest('.eqlens svg g.f.h'):null}
document.addEventListener('pointerover',function(e){if(e.pointerType!=='mouse'||pinned)return;var g=term(e.target);if(g&&(!cur||cur.g!==g))show(g)});
document.addEventListener('pointerout',function(e){if(e.pointerType!=='mouse'||pinned||!cur)return;
 var g=term(e.target);if(g&&g===cur.g&&!g.contains(e.relatedTarget))hide()});
document.addEventListener('focusin',function(e){if(pinned)return;var g=term(e.target);if(g)show(g)});
document.addEventListener('focusout',function(e){if(!pinned&&term(e.target))hide()});
function press(g){if(pinned&&cur&&cur.g===g){hide();return}show(g);if(cur)pinned=true}
document.addEventListener('click',function(e){var g=term(e.target);
 // A symbol that opens a tier swaps the drawing: the card would point at nothing.
 if(!g||g.classList.contains('x')){hide();return}press(g)});
document.addEventListener('keydown',function(e){if(e.key==='Escape'){hide();return}
 if(e.key!=='Enter'&&e.key!==' ')return;var g=term(e.target);if(g&&!g.classList.contains('x')){e.preventDefault();press(g)}});
window.addEventListener('resize',function(){if(cur)show(cur.g)});
function setup(){document.querySelectorAll('.eqlens').forEach(function(f){if(f.__popped||!f.querySelector('script.eqlens-pops'))return;
 f.__popped=1;var d=cards(f);f.querySelectorAll('svg').forEach(function(svg){var seen={};
  svg.querySelectorAll('g.f.h').forEach(function(g){var i=pick(g,f);if(i<0||seen[i])return;seen[i]=1;
   g.setAttribute('tabindex','0');g.setAttribute('role','button');
   g.setAttribute('aria-label',d[i].g+(d[i].t?', '+d[i].t:'')+(d[i].n?': '+d[i].n:''))})})})}
window.__eqlensPop=setup;setup();
})();"""
