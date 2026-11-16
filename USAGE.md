# Usage

Install is on the [README](README.md). If you are an LLM, follow the skill instead of this page: [`.grok/skills/eqlens/SKILL.md`](.grok/skills/eqlens/SKILL.md).

```bash
eqlens 'x=\frac{-b\pm\sqrt{b^{2}-4ac}}{2a}'
eqlens -o formula.svg 'E=mc^2'
eqlens -o formula.png 'E=mc^2'
eqlens 'E=mc^2' > formula.svg
eqlens --format png 'e^{i\pi}+1=0' | imgcat
```

On iTerm2, WezTerm, and Kitty the picture is inline, as a PNG, because a terminal paints pixels. Everywhere else the default is an SVG: a file from `-o`, the text itself through a pipe, or a path to a new file on a terminal that cannot show images. `-o name.png` or `--format png` gives a PNG. The two are the same picture.

<p align="center">
  <img src="docs/quadratic.png" alt="Quadratic formula" width="420"><br>
  <img src="docs/gaussian.png" alt="Gaussian integral" width="420"><br>
  <img src="docs/bayes.png" alt="Bayes" width="420">
</p>

## Ledger

`--legend` colors each Greek letter in the formula and lists it underneath with its English name in the same color. The same letter keeps the same color every time. Named symbols that are not Greek come next: "h bar", "del", "partial", "expectation". After those, each accent, subscript, and superscript is read aloud once: "ψ hat", "x sub i", "c squared", "∫ from −∞", "∫ to ∞".

A mark that is not arithmetic says what it usually means, once, in a dim line under its name. `u^\star` reads "u star", then "A marked u: often the best one, or its complex conjugate. Not a power." The same goes for transpose, dagger, prime, inverse, hat, bar, tilde, and dot. `A_e^\top` reads "A sub e transpose". A subscript that is already a word, as in `N_{\mathrm{dense}}`, gets no row.

```bash
eqlens --legend '\psi(x)=\int_{-\infty}^{\infty}\hat{\psi}(\xi)\,e^{2\pi i x \xi}\,d\xi'
```

<p align="center">
  <img src="docs/legend.png" alt="A Fourier integral with psi, xi, and pi colored in the formula and named in a ledger, then the integral limits, psi hat, and the exponent" width="640">
</p>

## What a symbol means here

`--define 'KEY=meaning'` gives a symbol its meaning in this formula. It gets a color and a row. `KEY` is the TeX of the symbol: `P`, `A_e`, `\epsilon`, `u^\star`.

A constant can carry its value. `$...$` in a meaning draws as math: `--define 'c=the speed of light, $299\,792\,458$ m/s'`. `--introspect` asks Claude to do this for constants it is sure of.

```bash
eqlens --legend \
  --define 'P=keeps the part of the noise the cell can see' \
  --define 'A_e=squeezes a cell of fine tokens into one' \
  --define 'u^\star=the target the model is trained on' \
  'u^\star=P\,\epsilon-x_0,\qquad P=A_eA_e^\top'
```

<p align="center">
  <img src="docs/define.png" alt="A formula whose P, A sub e, and u star are colored, with a ledger giving the meaning of each" width="640">
</p>

## Tiers: what a symbol is made of

`--tier 'KEY=formula'` says what a symbol is made of. The formula `KEY = formula` is drawn under that symbol's row, set in, with its own rows. A symbol in there can have a tier too, four deep at most.

```bash
eqlens --brief \
  --define 'P=keeps the coarse part' \
  --tier 'P=A_eA_e^\top' \
  --tier 'A_e=VU^\top' \
  'v=P\,u_a+\frac{(I-P)\,(x_t+u_a)}{\sigma}'
```

A symbol is one thing in every tier: the same color, listed once under the first formula that has it, and lit up everywhere when you point at it. A `--define` reaches a symbol inside a tier. A tier that names itself opens once and stops.

`eqlens --inspect` with the same `--tier` flags prints the whole tree as JSON, so you can see what the next level holds before you write it.

## Buttons: Expand and Copy

Name the output `.html`, or pass `--format html`, to get a fragment for a web page: the SVG under a small bar with two buttons.

- **Copy** puts the formula's TeX on the clipboard.
- **Expand** is there when the formula has tiers. The drawing starts with them shut and Expand opens them; Collapse shuts them again.

```bash
eqlens --brief --tier 'P=A_eA_e^\top' -o recover.html 'v=P\,u_a+\frac{(I-P)\,(x_t+u_a)}{\sigma}'
```

The fragment carries its own style and one short script. The SVG and PNG have no script in them. In an SVG or PNG the tiers are always open.

## Shader: GLSL for WebGL2 and Shadertoy

Name the output `.glsl` or `.frag`, or pass `--format glsl`, to get a fragment shader that draws the formula on the GPU. It is the same picture as the PNG, ledger and notes included, and it stays sharp at any size: every glyph outline is in the shader as line segments, and each pixel works out how far it is from the nearest edge. Nothing is loaded from a texture or a font.

```bash
eqlens --legend -o euler.frag 'e^{i\pi}+1=0'
eqlens --format glsl 'E=mc^2' > emc2.glsl
```

[The demo page](https://claude.ai/artifact/Q6151o5gGRHZBegqGHh2sV) draws the five equations of the TokenStream paper ([arXiv 2611.16897](https://arxiv.org/abs/2611.16897)) this way, with hover, zoom, and Copy for Shadertoy.

The file is a whole WebGL2 (GLSL ES 3.00) fragment shader. Draw a full-screen triangle and set two uniforms, named the way Shadertoy names them:

- `iResolution`, a `vec3`: the canvas size in pixels.
- `iMouse`, a `vec4`: the pointer in pixels from the bottom left. Pointing at a symbol lights it, its other appearances, and its row, and dims the rest, as hovering does in the SVG. `(0, 0)` means no pointer.

The formula is fitted to the canvas and centered. A card has its opaque background; a bare formula is transparent, and the color comes out premultiplied, as a WebGL canvas expects.

For Shadertoy, paste only the part between the lines `// ---- Shadertoy: paste from here ----` and `// ---- Shadertoy: paste to here ----`. It has a `mainImage` and no `#version` or uniforms of its own. Shadertoy only moves `iMouse` while the button is down, so there you click and drag to light a symbol.

A bare formula is about 10 KB of shader; a card with a ledger is 50 to 120 KB. The `--tips`, `--no-credit`, and `--dpi` flags change nothing in a shader, and it has no mark in the corner. `eqlensd` serves the same thing at `/glsl`.

## The mark in the corner

An SVG card has a small mark in its bottom right corner that links to [scrya.com/eqlens](https://scrya.com/eqlens). It is inside the SVG as data, so a drawing fetches nothing. `--no-credit` leaves it off. A bare formula with no card, and a PNG, have none.

## Let Claude say what the parts mean

`--introspect` asks Claude what the symbols and sub-expressions stand for in this formula, and draws them as if you had written the `--define` lines yourself. It also adds one line saying what the formula is.

```bash
python3 -m pip install 'eqlens[ai]'
export ANTHROPIC_API_KEY=...
eqlens --introspect -o einstein.svg 'G_{\mu\nu}+\Lambda g_{\mu\nu}=\frac{8\pi G}{c^4}T_{\mu\nu}'
```

Where a part is defined by a formula of its own, Claude gives that as a tier. Claude picks the parts worth explaining, such as `G_{\mu\nu}` as a whole and not μ and ν apart. Every part it names is checked against the typeset formula, and one that is not there is dropped. A `--define` of your own wins over Claude's for the same symbol. `--context 'from a paper on video diffusion'` tells it where the formula comes from.

Each call is one request to the Claude API, on your account. To ask once and keep the answer, add `--inspect`: it prints the meanings as JSON and draws nothing. Paste the `define` and `tier` items into your own `--define` and `--tier` flags or build script, and later runs need no key.

```bash
eqlens --introspect --inspect 'i\hbar\frac{\partial}{\partial t}\Psi=\hat{H}\Psi'
```

`--inspect` alone needs no key and asks nobody. It lists what is in the formula: each symbol, how it is said, and how many times it appears.

The model is `claude-opus-5-5`. Set `EQLENS_MODEL` to use another.

## Hover

Open the SVG in a browser, or put it inline in a page. Point at a symbol: every place it appears lights up with its ledger row, and the rest dims. Point at a ledger row and the formula shows where that symbol is. No script is involved, only CSS inside the SVG.

Inline means the `<svg>` element itself is in the HTML. Inside `<img>` the same file is a still picture, because a browser does not let an image react to the pointer.

```astro
---
import eq from '../eq/target.html?raw'
---
<Fragment set:html={eq} />
```

That is the `.html` fragment, with its buttons. A bare `.svg` goes in the same way inside a `<figure>`.

An inline SVG takes its colors from the page when the page sets them:

```css
figure svg { --eq-fg: #1f2328; --eq-bg: #ffffff; --eq-dim: #57606a; --eq-mark: #424a53; }
```

Each SVG scopes its own ids and styles, so many can share a page.

## A few flags

`eqlens --help` lists them.

| Flag | What it does |
| --- | --- |
| `--legend` | Color Greek, and name Greek, accents, subscripts, and superscripts |
| `--brief` | `--legend` without plain subscripts and powers: only the rows with something to say |
| `--tips` | SVG only: also pop up a browser tooltip with the name and meaning. Off by default, since the row that lights up says the same |
| `--tier 'KEY=formula'` | What a symbol is made of, drawn under its row. Repeat for more, and for deeper levels |
| `--no-credit` | Leave the small eqlens mark off an SVG card |
| `--introspect` | Ask Claude what the parts mean and draw them. Needs `eqlens[ai]` and an API key |
| `--context 'text'` | With `--introspect`: where the formula comes from |
| `--inspect` | Print what is in the formula as JSON and draw nothing |
| `--define 'KEY=meaning'` | Say what a symbol means here. Repeat for more |
| `--note 'text'` | A short note in fine print under the formula. Repeat for more lines. `$...$` renders as math |
| `-o file` | Write a file, print its absolute path, and do not display it. `.png` writes a PNG, `.html` a fragment with buttons, anything else an SVG |
| `--format svg\|png\|html` | Choose the format whatever the file is called. `html` adds the Copy and Expand buttons |
| `--font sans\|serif\|stix\|cm` | Typeface. `stix` and `cm` look like a printed paper |
| `--local` | Render in this process |
| `--bg '#12141a'` | Background. A bare formula is transparent by default; a card is dark |
| `--color '#f2f2f7'` | Color of everything that has no color of its own |
| `--dpi 220` | PNG resolution |

`eqlensd` is optional. It serves `/svg`, `/png`, and `/html` on `http://127.0.0.1:8765`. When it is running, `eqlens` uses it.

One formula per call. matplotlib mathtext: fractions, roots, integrals, sums, subscripts, superscripts, accents, `\mathrm`, `\mathbb`, `\mathcal`, `\text`, and Greek commands. No `\begin{...}` environments, no preamble, no `\color`, no TikZ. [`tests/equations.py`](tests/equations.py) lists some fifty formulas from physics, quantum physics, and machine learning that are drawn in the tests.

## From Python

```python
from eqlens.render import render_svg, render_png, render_html

svg = render_svg(r"e^{i\pi}+1=0", legend=True, define=["e=Euler's number"])
png = render_png(r"e^{i\pi}+1=0", legend=True, dpi=220)

from eqlens.introspect import inspect, introspect

parts = inspect(r"u^\star=P\,\epsilon-x_0")       # no key needed
found = introspect(r"u^\star=P\,\epsilon-x_0")    # asks Claude
svg = render_svg(found["tex"], brief=True, define=found["define"], tier=found["tier"], notes=[found["about"]])
page = render_html(found["tex"], brief=True, define=found["define"], tier=found["tier"])
```

## Claude Code

The pane is on the [README](README.md#claude-code). `/eqlens` draws into it. The flags are the same ones in the table above.

## It used to be mathcat

The command was `mathcat` and the server `mathd` before 0.2. Both names still run. `MATHCAT_URL` is still read when `EQLENS_URL` is not set.
