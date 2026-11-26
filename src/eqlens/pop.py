"""Popovers for the HTML output: point at a symbol in the formula and a small card opens under it.

The card says how the symbol is read and what it means. When the formula can
be worked out, it also draws the one picture that fits any formula: the result
as this symbol alone runs across its range, with a dot that travels the curve
and a line of numbers that follows it. Nothing here is written for one
formula. A formula that cannot be worked out as written (a derivative, a sum,
an operator) still gets the words, and gets the picture when ``expr`` gives a
case of it.

One kind of formula gets a picture of its own. A formula that is one part over
the sum of all the parts, such as softmax or a Boltzmann weight, is a share of
a whole, and a share is easier to see as bars than as a curve: the card draws
one bar for the part and one for each of a few others, and as the symbol runs
across its range its bar grows, the others shrink, and together they always
come to 1. It is read from the shape of the formula, not from its name.

A function the formula applies, ``\\exp`` or ``\\ln``, gets a card too when it
has a ledger row: the curve of that function alone, over the values that what
is inside it really takes in this formula. So the card for exp in a bell curve
shows that its inside never rises above 0 and its result stays between 0 and 1.

A card can carry a link to somewhere that explains the symbol further.

``cards`` makes the data, one item per ledger row. ``STYLE`` and ``SCRIPT`` go
in the fragment once and serve every eqlens figure on the page.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from urllib.parse import urlsplit

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
    link: Sequence[str] = (),
) -> list[dict]:
    """One card per row, in row order: ``g`` the symbol, ``t`` its title, ``n`` its note, ``c`` its color.

    A symbol the formula can be worked out for also has ``lo``, ``hi``, ``at``
    (its range and where it stands), ``ys`` (the result across the range,
    None where there is none), ``st`` (its step, when it moves in steps), ``out`` (what the result is called), and the
    units ``u`` and ``ou``. A constant has ``v``, its value. What the formula
    gives has ``now``, the result where every symbol stands. ``plot`` False
    keeps the words and leaves the numbers out: for a formula of matrices or
    tensors, which reads as arithmetic but is not a curve.

    A formula that is one part over the sum of all parts gives the symbol that
    part turns on ``bs`` as well: the share of each bar at each step, its own
    first, and ``bx``, where the other bars' symbols stand. ``link`` items are
    ``"KEY=URL words to show"``: that symbol's card gets ``m``, the address and
    the words.
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

    _links(rows, found, link)
    if not plot:
        return found
    # Imported here: the bench imports the renderer, and the renderer imports this.
    from eqlens.bench.spec import build, curve, work_out

    try:
        spec = build(tex, expr=expr, solve=solve, sets=sets, define=define, tier=tier, constant=constant, shared=shared)
    except FormulaError:
        if not expr and not solve and _shares(tex, rows, found, sets):
            return found
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
    _functions(spec, where, found)
    if output["key"]:
        index = where.get(_shape(output["key"]))
        now = _round(work_out(spec))
        if index is not None and now is not None and "ys" not in found[index]:
            found[index].update(now=now, u=output["unit"])
    return found


_INSIDE = "what is inside"
_APPLIED = {"exp": (r"\exp", math.exp), "ln": (r"\ln", math.log)}


def _calls(node: tuple):
    """Each place the expression applies exp or ln, as ``(name, what is inside)``. ``e`` to a power is exp."""
    if not isinstance(node, tuple) or node[0] in ("num", "sym", "const"):
        return
    if node[0] == "call" and node[1] in _APPLIED:
        yield node[1], node[2]
    elif node[0] == "pow" and node[1] == ("const", "e"):
        yield "exp", node[2]
    for child in node[1:]:
        yield from _calls(child)


def _functions(spec: dict, where: dict[tuple, int], found: list[dict]) -> None:
    """Give exp and ln their cards: the function alone, across what its inside takes as the symbols run their ranges."""
    from eqlens.bench.expr import symbols_in, value
    from eqlens.bench.spec import tree

    env = {entry["key"]: entry["value"] for entry in spec["symbols"]}
    ranges = {entry["key"]: (entry["min"], entry["max"]) for entry in spec["symbols"] if entry["role"] != "constant"}
    done: set[int] = set()
    for name, inside in _calls(tree(spec)):
        key, apply = _APPLIED[name]
        index = where.get(_shape(key))
        if index is None and name == "exp":
            # e^{...} has no \exp to point at: the card goes to e when the ledger has a row for it.
            index = where.get(_shape("e"))
        if index is None or index in done or "ys" in found[index]:
            continue

        def at(changes: dict) -> float | None:
            try:
                return _round(value(inside, {**env, **changes}))
            except (FormulaError, ArithmeticError, ValueError):
                return None

        home = at({})
        if home is None:
            continue
        seen = [home]
        # The symbol the formula is drawn against, when it is in there. With none, every symbol in there has its turn.
        inner = symbols_in(inside)
        for symbol in [spec.get("sweep")] if spec.get("sweep") in inner else inner:
            if symbol in ranges:
                lo, hi = ranges[symbol]
                seen += [at({symbol: lo + (hi - lo) * step / STEPS}) for step in range(STEPS + 1)]
        seen = [x for x in seen if x is not None and (name != "ln" or x > 0)]
        if not seen:
            continue
        lo, hi = min(seen), max(seen)
        if hi - lo < 1e-9:
            lo, hi = lo - 1.0, hi + 1.0
            if name == "ln":
                lo = max(lo, hi / 100)
        try:
            ys = [_round(apply(lo + (hi - lo) * step / STEPS)) for step in range(STEPS + 1)]
        except (ArithmeticError, ValueError):
            continue
        if any(y is None for y in ys):
            continue
        done.add(index)
        found[index].update(lo=lo, hi=hi, at=min(hi, max(lo, home)), ys=ys, out=name, ax=_INSIDE, u="", ou="")


def _links(rows: Sequence[Symbol], found: list[dict], link: Sequence[str]) -> None:
    for item in link or ():
        key, sep, rest = (item or "").partition("=")
        key, parts = key.strip().strip("$").strip(), rest.split(None, 1)
        if not sep or not key or not parts:
            raise FormulaError("--link takes KEY=URL, with words to show after the URL if you like")
        url = parts[0]
        host = urlsplit(url).hostname if url.startswith(("https://", "http://")) else None
        if not host:
            raise FormulaError(f"--link {key}: the address must start with https:// or http://")
        shape = _shape(key)
        index = next((i for i, row in enumerate(rows) if _shape(row.key) == shape), None)
        if index is None:
            raise FormulaError(f"--link {key}: that symbol has no row in the ledger. Give it one with --define")
        found[index]["m"] = [url, parts[1].strip() if len(parts) > 1 else host.removeprefix("www.")]


_BARS = 4
_SUM = re.compile(
    r"\\sum\s*_\s*(?:\{\s*([A-Za-z])[^{}]*\}|([A-Za-z]))\s*(?:\^\s*(?:\{([^{}]*)\}|(\\?[A-Za-z0-9]+)))?"
)


def _braced(tex: str, at: int) -> tuple[str, int] | None:
    """The ``{...}`` group that starts at or after ``at``: what is inside it, and where it ends."""
    while at < len(tex) and tex[at].isspace():
        at += 1
    if at >= len(tex) or tex[at] != "{":
        return None
    depth = 0
    for i in range(at, len(tex)):
        if tex[i] == "\\":
            continue
        if tex[i] == "{" and tex[i - 1 : i] != "\\":
            depth += 1
        elif tex[i] == "}" and tex[i - 1 : i] != "\\":
            depth -= 1
            if depth == 0:
                return tex[at + 1 : i], i + 1
    return None


def _indexed(tex: str, index: str) -> str:
    """``tex`` with the subscript ``index`` marked, and its spaces gone, so two terms can be compared."""
    return re.sub(r"\s+", "", re.sub(rf"_\{{\s*{index}\s*\}}|_{index}(?![A-Za-z])", "_#", tex))


def _part_of_whole(tex: str) -> tuple[str, str, str, str] | None:
    """``OUT = \\frac{term_i}{\\sum_j term_j}``: what it gives, the term, its index, and the sum's upper end."""
    from eqlens.bench.expr import _split

    sides = _split(tex)
    if len(sides) != 2:
        return None
    right = sides[1].strip()
    head = re.match(r"\\[dt]?frac(?![A-Za-z])", right)
    top = _braced(right, head.end()) if head else None
    bottom = _braced(right, top[1]) if top else None
    if not bottom or right[bottom[1] :].strip():
        return None
    total = _SUM.match(bottom[0].strip())
    if not total:
        return None
    over = total.group(1) or total.group(2)
    body = _indexed(bottom[0].strip()[total.end() :], over)
    for index in sorted(set(re.findall(r"_\{?\s*([A-Za-z])\s*\}?", top[0]))):
        if index != over and _indexed(top[0], index) == body:
            return sides[0].strip(), top[0], index, (total.group(3) or total.group(4) or "").strip()
    return None


def _shares(tex: str, rows: Sequence[Symbol], found: list[dict], sets: Sequence) -> bool:
    """Give the symbol a share turns on its bars. False when the formula is not a part over the sum of all parts."""
    from eqlens.bench.expr import from_tex, symbols_in, value
    from eqlens.bench.spec import _sets

    shape = _part_of_whole(tex)
    if not shape:
        return False
    out, term, index, end = shape
    try:
        _none, _args, node = from_tex(term)
    except FormulaError:
        return False
    keys = symbols_in(node)
    turning = [key for key in keys if "_#" in _indexed(key, index)]
    if len(turning) != 1:
        return False
    key = turning[0]
    at = next((i for i, row in enumerate(rows) if _shape(row.key) == _shape(key)), None)
    if at is None:
        return False
    given = {_shape(entry["key"]): entry for entry in _sets(sets)}
    mine = given.get(_shape(key), {})
    lo, hi = mine.get("min"), mine.get("max")
    if lo is None:
        middle = mine.get("value", 1.0)
        lo, hi = middle - 3.0, middle + 3.0
    count = given.get(_shape(end), {}).get("value") if end else None
    count = max(2, min(6, int(count))) if count else _BARS
    others = [lo + (hi - lo) * (k + 1) / count for k in range(count - 1)]
    env = {name: given.get(_shape(name), {}).get("value", 1.0) for name in keys}

    def weigh(x: float) -> float:
        return value(node, {**env, key: x})

    try:
        fixed = [weigh(x) for x in others]
        steps = []
        for step in range(STEPS + 1):
            parts = [weigh(lo + (hi - lo) * step / STEPS), *fixed]
            whole = sum(parts)
            if not math.isfinite(whole) or whole <= 0 or min(parts) < 0:
                return False
            steps.append([round(part / whole, 4) for part in parts])
    except (FormulaError, ArithmeticError, ValueError):
        return False
    found[at].update(
        lo=lo, hi=hi, at=mine.get("value", lo + (hi - lo) / 3), ys=[row[0] for row in steps], bs=steps,
        bx=[_round(x) for x in others], out=plain(f"${out}$"), ou="", u=mine.get("unit", ""),
    )
    return True


def embed(found: Sequence[dict]) -> str:
    """The cards as a block of JSON for the fragment. Empty when no card has anything to say."""
    if not any(card["t"] or card["n"] or "ys" in card or "v" in card or "now" in card or "m" in card for card in found):
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
    ".eqlens-pop.open{opacity:1;visibility:visible;pointer-events:auto;transform:none;transition:opacity .18s ease,transform .18s ease}"
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
    ".eqlens-pop-more{margin-top:8px!important;font-size:13px}"
    ".eqlens-pop-more a{color:var(--eq-link,#79c0ff);text-decoration:underline;text-underline-offset:2px}"
    "@media (prefers-reduced-motion:reduce){.eqlens-pop{transition:none}}"
)

# One set of listeners for every eqlens figure on the page. A later fragment calls the first one's setup again.
SCRIPT = r"""(function(){
if(window.__eqlensPop){window.__eqlensPop();return}
var NS='http://www.w3.org/2000/svg',W=300,H=104,L=4,R=4,T=8,B=20;
var cur=null,pinned=false,raf=0,still=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
function cards(f){if(!f.__pops){var s=f.querySelector('script.eqlens-pops');
 try{f.__pops=JSON.parse(s.textContent)}catch(e){f.__pops=[]}}return f.__pops}
function full(c){return c&&(c.t||c.n||c.ys||c.v!=null||c.now!=null||c.m)}
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
  '<p class="eqlens-pop-read"></p><p class="eqlens-pop-note"></p><p class="eqlens-pop-more"><a target="_blank" rel="noopener"></a></p>';f.appendChild(p);return p}
function plot(p,c){var svg=p.querySelector('svg'),read=p.querySelector('.eqlens-pop-read');
 cancelAnimationFrame(raf);svg.textContent='';
 if(!c.ys){svg.style.display='none';
  read.textContent=c.v!=null?c.g+' = '+num(c.v)+unit(c.u):c.now!=null?c.g+' = '+num(c.now)+unit(c.u)+' as it stands':'';
  read.style.display=read.textContent?'':'none';return}
 svg.style.display='';read.style.display='';
 var ys=c.ys,n=ys.length-1,s=span(ys),lo=s[0],hi=s[1],ink=c.c||'currentColor',put;
 if(c.bs){
  // A share of a whole: one bar for this part and one for each of the others. They always come to 1.
  var K=c.bs[0].length,gw=(W-L-R)/K,bw=Math.min(68,gw*.72),base=H-B+4,top=T+12,bars=[],pct=[],mine;
  svg.appendChild(el('line',{x1:L,x2:W-R,y1:base,y2:base,stroke:'currentColor','stroke-opacity':.22}));
  for(var k=0;k<K;k++){var cx=L+gw*(k+.5),r=el('rect',{x:cx-bw/2,width:bw,rx:3,fill:k?'currentColor':ink,'fill-opacity':k?.28:1}),
    t=el('text',{x:cx,'text-anchor':'middle'}),b=el('text',{x:cx,y:H-4,'text-anchor':'middle'},k?num(c.bx[k-1]):'');
   svg.appendChild(r);svg.appendChild(t);svg.appendChild(b);bars.push(r);pct.push(t);if(!k){mine=b;b.style.fill=ink}}
  put=function(u){var q=u*n,i=Math.min(n-1,Math.floor(q)),f=q-i,x=c.lo+(c.hi-c.lo)*u,me=0;
   for(var k=0;k<K;k++){var v=c.bs[i][k]+(c.bs[i+1][k]-c.bs[i][k])*f,h=Math.max(1,v*(base-top));
    bars[k].setAttribute('y',base-h);bars[k].setAttribute('height',h);pct[k].setAttribute('y',base-h-3);
    pct[k].textContent=Math.round(v*100)+'%';if(!k)me=v}
   mine.textContent=num(x);
   read.textContent=c.g+' = '+num(x)+unit(c.u)+'  →  '+c.out+' = '+num(me)+'. All '+K+' add up to 1.'}}
 else{
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
 svg.appendChild(el('text',{x:W/2,y:H-4,'text-anchor':'middle'},(c.ax||c.g)+unit(c.u)));
 var hair=el('line',{y1:T,y2:H-B+4,stroke:ink,'stroke-opacity':.45}),dot=el('circle',{r:4.5,fill:ink,stroke:'var(--eq-pop-bg,#1c1f27)','stroke-width':2});
 svg.appendChild(hair);svg.appendChild(dot);
 put=function(u){if(c.st)u=Math.round(u*n)/n;var q=u*n,i=Math.min(n-1,Math.floor(q)),a=ys[i],b=ys[i+1],y=(a==null||b==null)?null:a+(b-a)*(q-i),x=c.lo+(c.hi-c.lo)*u;
  hair.setAttribute('x1',X(u));hair.setAttribute('x2',X(u));
  if(y==null){dot.style.display='none'}else{dot.style.display='';dot.setAttribute('cx',X(u));dot.setAttribute('cy',Y(y))}
  read.textContent=(c.ax||c.g)+' = '+num(x)+unit(c.u)+'  →  '+c.out+' = '+num(y)+(y==null?'':unit(c.ou))}}
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
  note.style.display=c.n?'':'none';
  var more=p.querySelector('.eqlens-pop-more'),a=more.firstChild,ok=c.m&&/^https?:\/\//.test(c.m[0]);
  more.style.display=ok?'':'none';if(ok){a.href=c.m[0];a.textContent=c.m[1]+' ↗'}plot(p,c)}
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
document.addEventListener('click',function(e){if(e.target.closest&&e.target.closest('.eqlens-pop'))return;var g=term(e.target);
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
