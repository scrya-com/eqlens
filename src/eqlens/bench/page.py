"""The bench as a web page: the eqlens drawing, a slider for every symbol, and a plot that follows.

One file with no outside scripts. Pointing at a symbol in the drawing lights
its slider, and pointing at a slider lights the symbol. Beside each slider is
a small plot of the result as that symbol alone crosses its range.

A function the formula applies, exp or ln, has a row of its own with no
slider: what is inside it now, what comes out, and the function's curve with a
dot that moves as the sliders do.
"""

from __future__ import annotations

import html
import json

from eqlens.bench.expr import to_js
from eqlens.bench.spec import tree
from eqlens.engine import FormulaError
from eqlens.render import render

_CSS = """
:root{--bg:#0b0d12;--card:#12141a;--fg:#f2f2f7;--dim:#8b949e;--line:#262a33}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
.bench{max-width:900px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:20px;margin:0 0 4px;text-wrap:balance}
.about{color:var(--dim);margin:0 0 16px}
.card{background:var(--card);border-radius:12px;padding:8px;overflow-x:auto;text-align:center}
.card svg{max-width:100%;height:auto}
.plot{background:var(--card);border-radius:12px;margin-top:12px;padding:12px}
.plot canvas{display:block;width:100%;height:310px}
.read{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:8px 4px 0;flex-wrap:wrap}
.read output{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}
.read button{font:500 12px/1 inherit;color:var(--dim);background:transparent;border:1px solid currentColor;
border-radius:6px;padding:6px 10px;cursor:pointer}
.read button:hover,.read button:focus-visible{color:var(--fg)}
.rows{margin-top:12px;display:grid;gap:8px}
.row{background:var(--card);border-radius:12px;padding:10px 12px;display:grid;
grid-template-columns:minmax(64px,auto) 1fr 92px 110px;gap:4px 12px;align-items:center;
border:1px solid transparent;transition:opacity .12s,border-color .12s}
.row .glyph{font-size:20px;font-weight:600}
.row .says{color:var(--dim);font-size:12px;display:block}
.row input[type=range]{width:100%;accent-color:var(--c)}
.row input[type=number]{width:100%;background:transparent;color:var(--fg);border:1px solid var(--line);
border-radius:6px;padding:5px 6px;font:inherit;font-variant-numeric:tabular-nums}
.row canvas{width:110px;height:38px;display:block}
.row .means{grid-column:1/-1;color:var(--dim);font-size:13px;margin:0}
.row.fixed{grid-template-columns:minmax(64px,auto) 1fr}
.row.applied{grid-template-columns:minmax(64px,auto) 1fr 110px}
.row.applied output{font-variant-numeric:tabular-nums}
.bench.lit .row{opacity:.4}
.bench.lit .row.on{opacity:1;border-color:var(--c)}
.foot{color:var(--dim);font-size:13px;margin-top:16px}
.foot svg{vertical-align:middle;max-width:100%;height:auto}
.foot p{margin:6px 0}
@media (max-width:560px){.row{grid-template-columns:1fr 92px}.row canvas{display:none}}
"""

_JS = r"""
(function(){
var S=SPEC,root=document.getElementById('bench'),main=document.getElementById('main'),out=document.getElementById('out');
var v={},start={};S.symbols.forEach(function(s){v[s.name]=s.value;start[s.name]=s.value});
var moving=S.symbols.filter(function(s){return s.role!=='constant'});
var sweep=moving.filter(function(s){return s.key===S.sweep})[0]||moving[0];
function f(env){var y;try{y=F(env)}catch(e){y=NaN}return (typeof y==='number'&&isFinite(y))?y:NaN}
function fmt(x){if(!isFinite(x))return 'no real value';if(x===0)return '0';var a=Math.abs(x);
 if(a>=1e5||a<1e-3)return x.toExponential(3).replace(/\.?0+e/,'e');return String(+x.toPrecision(4))}
function num(x){var a=Math.abs(x);return (a!==0&&(a>=1e6||a<1e-4))?x.toExponential(4).replace(/\.?0+e/,'e'):String(+x.toPrecision(6))}
function run(s,env,n){var xs=[],ys=[],e={},k;for(k in env)e[k]=env[k];if(s.step)n=Math.round((s.max-s.min)/s.step);
 for(var i=0;i<=n;i++){var x=s.min+(s.max-s.min)*i/n;e[s.name]=x;xs.push(x);ys.push(f(e))}return [xs,ys]}
function span(lists){var all=[];lists.forEach(function(ys){ys.forEach(function(y){if(!isNaN(y))all.push(y)})});
 if(!all.length)return [0,1];all.sort(function(a,b){return a-b});
 var lo=all[0],hi=all[all.length-1],p=function(q){return all[Math.min(all.length-1,Math.floor(q*all.length))]};
 var a=p(.03),b=p(.97);if(b>a&&(hi-lo)>40*(b-a)){lo=a-(b-a);hi=b+(b-a)}
 if(hi===lo){hi+=Math.abs(hi)||1;lo-=Math.abs(lo)||1}var pad=(hi-lo)*.06;return [lo-pad,hi+pad]}
function ticks(lo,hi,n){var raw=(hi-lo)/n,m=Math.pow(10,Math.floor(Math.log10(raw))),r=raw/m,
 step=(r<1.5?1:r<3?2:r<7?5:10)*m,t=[];for(var x=Math.ceil(lo/step)*step;x<=hi+step*1e-9;x+=step)t.push(Math.abs(x)<step*1e-9?0:x);return t}
function size(c){var d=window.devicePixelRatio||1,w=c.clientWidth,h=c.clientHeight;
 if(c.width!==Math.round(w*d)||c.height!==Math.round(h*d)){c.width=Math.round(w*d);c.height=Math.round(h*d)}
 var g=c.getContext('2d');g.setTransform(d,0,0,d,0,0);g.clearRect(0,0,w,h);return [g,w,h]}
function path(g,xs,ys,X,Y,s,r){if(s&&s.step){g.save();g.setLineDash([]);g.fillStyle=g.strokeStyle;for(var j=0;j<xs.length;j++){
 if(!isNaN(ys[j])){g.beginPath();g.arc(X(xs[j]),Y(ys[j]),r||3.5,0,7);g.fill()}}g.restore();return}
 var pen=false;g.beginPath();for(var i=0;i<xs.length;i++){
 if(isNaN(ys[i])){pen=false;continue}if(pen)g.lineTo(X(xs[i]),Y(ys[i]));else g.moveTo(X(xs[i]),Y(ys[i]));pen=true}g.stroke()}
function drawMain(){var q=size(main),g=q[0],w=q[1],h=q[2],L=58,R=14,T=12,B=40;
 var now=run(sweep,v,240),was=run(sweep,start,240),ys=span([now[1],was[1]]);
 var X=function(x){return L+(x-sweep.min)/(sweep.max-sweep.min)*(w-L-R)},Y=function(y){return h-B-(y-ys[0])/(ys[1]-ys[0])*(h-T-B)};
 g.font='12px system-ui,sans-serif';g.lineWidth=1;g.strokeStyle='#262a33';g.fillStyle='#8b949e';
 g.textAlign='center';g.textBaseline='top';ticks(sweep.min,sweep.max,7).forEach(function(t){
  g.beginPath();g.moveTo(X(t),T);g.lineTo(X(t),h-B);g.stroke();
  g.textAlign=X(t)>w-R-24?'right':'center';g.fillText(fmt(t),Math.min(X(t),w-2),h-B+6)});
 g.textAlign='right';g.textBaseline='middle';ticks(ys[0],ys[1],5).forEach(function(t){
  g.beginPath();g.moveTo(L,Y(t));g.lineTo(w-R,Y(t));g.stroke();g.fillText(fmt(t),L-8,Y(t))});
 g.textAlign='right';g.textBaseline='bottom';g.fillStyle=sweep.color;g.fillText(sweep.shown+(sweep.unit?' ('+sweep.unit+')':''),w-R,h);
 g.save();g.beginPath();g.rect(L,T,w-L-R,h-T-B);g.clip();
 g.setLineDash([4,4]);g.strokeStyle='#4a5160';g.lineWidth=1.5;path(g,was[0],was[1],X,Y,sweep,2.5);g.setLineDash([]);
 g.strokeStyle=sweep.color;g.lineWidth=2.5;g.lineJoin='round';path(g,now[0],now[1],X,Y,sweep,4);
 var y=f(v);if(!isNaN(y)){g.fillStyle='#f2f2f7';g.beginPath();g.arc(X(v[sweep.name]),Y(y),5,0,7);g.fill()}
 g.restore();out.textContent=fmt(y)+(S.output.unit&&!isNaN(y)?' '+S.output.unit:'')}
function drawSpark(s,c){var q=size(c),g=q[0],w=q[1],h=q[2],d=run(s,v,60),ys=span([d[1]]);
 var X=function(x){return 3+(x-s.min)/(s.max-s.min)*(w-6)},Y=function(y){return h-4-(y-ys[0])/(ys[1]-ys[0])*(h-8)};
 g.strokeStyle=s.color;g.lineWidth=1.6;g.lineJoin='round';path(g,d[0],d[1],X,Y,s,d[0].length>30?1.2:2);
 var y=f(v);if(!isNaN(y)){g.fillStyle='#f2f2f7';g.beginPath();g.arc(X(v[s.name]),Y(y),3,0,7);g.fill()}}
var rows={};
moving.forEach(function(s){var el=root.querySelector('.row[data-name="'+s.name+'"]');
 rows[s.name]={el:el,range:el.querySelector('input[type=range]'),num:el.querySelector('input[type=number]'),spark:el.querySelector('canvas')}});
// A function the formula applies: its own curve over what its inside takes as the plotted symbol crosses its range.
var applied=[];root.querySelectorAll('.row.applied').forEach(function(el,i){
 applied.push({a:APPLIED[i],out:el.querySelector('output'),spark:el.querySelector('canvas')})});
function inside(a,env){var u;try{u=a.inside(env)}catch(e){u=NaN}return (typeof u==='number'&&isFinite(u))?u:NaN}
function drawApplied(p){var a=p.a,fn=a.fn==='ln'?Math.log:Math.exp,e={},k,lo=Infinity,hi=-Infinity,now=inside(a,v);
 for(k in v)e[k]=v[k];for(var i=0;i<=120;i++){e[sweep.name]=sweep.min+(sweep.max-sweep.min)*i/120;var u=inside(a,e);
  if(!isNaN(u)&&(a.fn!=='ln'||u>0)){lo=Math.min(lo,u);hi=Math.max(hi,u)}}
 if(!isNaN(now)&&(a.fn!=='ln'||now>0)){lo=Math.min(lo,now);hi=Math.max(hi,now)}
 var y=(isNaN(now)||(a.fn==='ln'&&now<=0))?NaN:fn(now);
 p.out.textContent=isNaN(y)?'no real value':'inside = '+fmt(now)+'  →  '+a.fn+' = '+fmt(y);
 var q=size(p.spark),g=q[0],w=q[1],h=q[2];if(!(hi>=lo))return;if(hi-lo<1e-9){lo-=1;hi+=1;if(a.fn==='ln')lo=Math.max(lo,hi/100)}
 var xs=[],ys=[];for(var j=0;j<=60;j++){var x=lo+(hi-lo)*j/60;xs.push(x);ys.push(fn(x))}
 var s=span([ys]),X=function(x){return 3+(x-lo)/(hi-lo)*(w-6)},Y=function(t){return h-4-(t-s[0])/(s[1]-s[0])*(h-8)};
 g.strokeStyle='#c9d1d9';g.lineWidth=1.6;g.lineJoin='round';path(g,xs,ys,X,Y);
 if(!isNaN(y)){g.fillStyle='#f2f2f7';g.beginPath();g.arc(X(now),Y(y),3,0,7);g.fill()}}
function draw(){drawMain();moving.forEach(function(s){drawSpark(s,rows[s.name].spark)});applied.forEach(drawApplied)}
function set(s,x,from){if(!isFinite(x))return;if(s.step)x=s.min+Math.round((x-s.min)/s.step)*s.step;v[s.name]=x;var r=rows[s.name];
 if(from!==r.range)r.range.value=x;if(from!==r.num)r.num.value=num(x);draw()}
moving.forEach(function(s){var r=rows[s.name];
 r.range.addEventListener('input',function(){set(s,parseFloat(r.range.value),r.range)});
 r.num.addEventListener('input',function(){set(s,parseFloat(r.num.value),r.num)})});
document.getElementById('reset').addEventListener('click',function(){moving.forEach(function(s){set(s,start[s.name])})});
// The drawing and the sliders light each other.
function light(index){root.querySelectorAll('.row.on').forEach(function(e){e.classList.remove('on')});
 if(index===null){root.classList.remove('lit');root.removeAttribute('data-lit');return}
 var hit=root.querySelectorAll('.row[data-row="'+index+'"]');hit.forEach(function(e){e.classList.add('on')});
 root.classList.toggle('lit',hit.length>0);root.setAttribute('data-lit',index)}
root.querySelectorAll('.row[data-row]').forEach(function(el){
 el.addEventListener('pointerenter',function(){light(el.getAttribute('data-row'))});
 el.addEventListener('pointerleave',function(){light(null)});
 el.addEventListener('focusin',function(){light(el.getAttribute('data-row'))});
 el.addEventListener('focusout',function(){light(null)})});
var card=root.querySelector('.card');
card.addEventListener('pointerover',function(e){var g=e.target.closest&&e.target.closest('g.h');if(!g){light(null);return}
 var m=/(?:^|\s)s(\d+)(?:\s|$)/.exec(g.getAttribute('class')||'');light(m?m[1]:null)});
card.addEventListener('pointerleave',function(){light(null)});
moving.forEach(function(s){rows[s.name].num.value=num(v[s.name])});
window.addEventListener('resize',draw);draw();
})();
"""


def _json(data) -> str:
    """JSON that is safe inside a script element."""
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _applied(spec: dict, node: tuple) -> list[tuple[dict, tuple]]:
    """Each of exp and ln the formula applies, once: its name, how it is said, the tip, its ledger row, and what is inside."""
    from eqlens.constants import defines as constant_defines
    from eqlens.legend import _NAMED, _shape, plain, plan
    from eqlens.pop import _APPLIED, _calls

    try:
        define = constant_defines(list(spec["constant"])) + list(spec["define"])
        _top, rows = plan(spec["tex"], legend=True, define=define, tier=spec["tier"], brief=True, known=False, shared=spec["shared"])
    except FormulaError:
        rows = []
    said = {command: (name, hint) for command, name, hint in _NAMED}
    found, seen = [], set()
    for fn, inside in _calls(node):
        if fn in seen:
            continue
        seen.add(fn)
        index = next((i for i, row in enumerate(rows) if _shape(row.key) == _shape(_APPLIED[fn][0])), None)
        found.append(({"fn": fn, "says": said[fn][0], "means": plain(said[fn][1]), "row": index}, inside))
    return found


def write(spec: dict, font: str = "sans") -> bytes:
    """The page as bytes: a whole HTML document."""
    node = tree(spec)
    names = {entry["key"]: entry["name"] for entry in spec["symbols"]}
    function = to_js(node, lambda key: "v." + names[key])
    card = render(
        spec["tex"], "svg", brief=True, define=spec["define"], tier=spec["tier"], constant=spec["constant"],
        shared=spec["shared"], notes=spec["notes"], known=False, font=font,
    ).decode("utf-8")
    try:
        computed = render(spec["computed"], "svg", color="#8b949e", font=font).decode("utf-8")
    except FormulaError:
        computed = html.escape(spec["expr"])
    esc = html.escape
    output = spec["output"]
    title = spec["name"] or "eqlens bench"

    rows = []
    lit = []
    for entry in spec["symbols"]:
        row = "" if entry["row"] is None else f' data-row="{entry["row"]}"'
        if entry["row"] is not None:
            lit.append(entry["row"])
        head = (
            f'<div><span class="glyph" style="color:{entry["color"]}">{esc(entry["shown"])}</span>'
            + (f'<span class="says">{esc(entry["says"])}</span>' if entry["says"] else "") + "</div>"
        )
        means = f'<p class="means">{esc(entry["means"])}</p>' if entry["means"] else ""
        if entry["role"] == "constant":
            unit = f' {esc(entry["unit"])}' if entry["unit"] else ""
            rows.append(
                f'<div class="row fixed" data-name="{esc(entry["name"])}"{row} style="--c:{entry["color"]}">{head}'
                f'<div>{entry["value"]:.6g}{unit} <span class="says">a constant: it does not change</span></div>{means}</div>'
            )
            continue
        step = entry.get("step") or (entry["max"] - entry["min"]) / 400
        fine = repr(entry["step"]) if entry.get("step") else "any"
        label = esc(entry["says"] or entry["shown"])
        unit = f' <span class="says">{esc(entry["unit"])}</span>' if entry["unit"] else ""
        rows.append(
            f'<div class="row" data-name="{esc(entry["name"])}"{row} style="--c:{entry["color"]}">{head}'
            f'<input type="range" min="{entry["min"]!r}" max="{entry["max"]!r}" step="{step!r}" value="{entry["value"]!r}" aria-label="{label}">'
            f'<div><input type="number" min="{entry["min"]!r}" max="{entry["max"]!r}" step="{fine}" value="{entry["value"]!r}" aria-label="{label}, as a number">{unit}</div>'
            f'<canvas aria-hidden="true"></canvas>{means}</div>'
        )
    applied = []
    for name, inside in _applied(spec, node):
        row = "" if name["row"] is None else f' data-row="{name["row"]}"'
        if name["row"] is not None:
            lit.append(name["row"])
        rows.append(
            f'<div class="row applied"{row} style="--c:#c9d1d9"><div><span class="glyph">{esc(name["fn"])}</span>'
            f'<span class="says">{esc(name["says"])}</span></div><output aria-live="off"></output>'
            f'<canvas aria-hidden="true"></canvas><p class="means">{esc(name["means"])}</p></div>'
        )
        applied.append(f'{{fn:{_json(name["fn"])},inside:function(v){{return {to_js(inside, lambda key: "v." + names[key])}}}}}')
    # Pointing at a slider dims the drawing and lights that symbol in it.
    glow = "".join(
        f'.bench[data-lit="{index}"] .card svg :is(.f,.r){{opacity:.28}}.bench[data-lit="{index}"] .card svg .s{index}{{opacity:1}}'
        for index in sorted(set(lit))
    )
    about = spec["about"] or ("One case of the formula, to try by hand." if spec.get("case") else "")
    data = {
        "sweep": spec["sweep"],
        "output": {"shown": output["shown"], "unit": output["unit"]},
        "symbols": [
            {name: entry.get(name) for name in ("key", "name", "shown", "role", "value", "min", "max", "step", "unit", "color")}
            for entry in spec["symbols"]
        ],
    }
    page = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{esc(title)}</title><style>{_CSS}{glow}</style></head>\n<body>"
        '<main class="bench" id="bench">'
        f"<h1>{esc(title)}</h1>" + (f'<p class="about">{esc(about)}</p>' if about else "")
        + f'<section class="card">{card.strip()}</section>'
        '<section class="plot"><canvas id="main" role="img" '
        f'aria-label="{esc(output["shown"])} plotted against {esc(next((e["shown"] for e in spec["symbols"] if e["key"] == spec["sweep"]), ""))}"></canvas>'
        f'<div class="read"><span><span style="color:{output["color"]};font-weight:600">{esc(output["shown"])}</span> = '
        '<output id="out" aria-live="polite"></output></span>'
        '<button type="button" id="reset">Reset</button></div></section>'
        f'<section class="rows">{"".join(rows)}</section>'
        f'<div class="foot"><p>Worked out as {computed.strip()}</p><p>{esc(spec["checked"][:1].upper() + spec["checked"][1:])}. '
        "The dashed curve is where the bench started.</p></div>"
        "</main>\n"
        f"<script>var SPEC={_json(data)};function F(v){{return {function}}}var APPLIED=[{','.join(applied)}];</script>\n"
        f"<script>{_JS}</script>\n</body></html>\n"
    )
    return page.encode("utf-8")
