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

## Buttons: Read, Expand, and Copy

Name the output `.html`, or pass `--format html`, to get a fragment for a web page: the SVG under a small bar of glyph buttons. Each one has no words on it; its name is in its tooltip and its `aria-label`.

- **Read** (a speech bubble) opens the whole formula in words, the way it is said aloud: "L equals the squared L2 norm of (1 minus M) elementwise times (v hat l minus v l), over the L1 norm of (1 minus M), plus …". It opens above the drawing, or below it when there is no room above, and never on top of it, so the page does not grow and the formula stays in view. Its speaker button reads it aloud with the browser's own voice. Escape or a click elsewhere closes it.
- **Expand** (two arrows) is there when the formula has tiers. The drawing starts with them shut and Expand opens them; Collapse shuts them again.
- **Copy** (two sheets) puts the formula's TeX on the clipboard, and shows a tick when it has.

The same reading is in every SVG as its `<desc>`, for screen readers, and at the top of a shader as a comment. `eqlens --read '<tex>'` prints it and draws nothing. In it a fraction bar is "over", `\|x\|_1` is "the L1 norm of x", `\odot` is "elementwise times", a one-letter label such as the layer in `v^l` is "v l" and not "v to the l", and a part that is more than one term keeps brackets so the reading says where it ends.

```bash
eqlens --brief --tier 'P=A_eA_e^\top' -o recover.html 'v=P\,u_a+\frac{(I-P)\,(x_t+u_a)}{\sigma}'
```

### A card under each symbol

In the fragment, point at a symbol in the formula, or tab to it, or tap it, and a small card opens under it. Click pins the card; Escape or a click elsewhere shuts it. The card has:

- the symbol, how it is said, and what it means (from `--legend`, `--define`, `--constant`);
- when the formula can be worked out, a plot of the result as that symbol alone runs across its range, with a dot that travels the curve and the numbers under it;
- for a constant, its value.

Nothing is written per formula: every formula gets the words, and every formula eqlens can read as arithmetic gets the plot. A formula with a derivative, a sum, or an operator gets the plot when `--expr` gives one case of it. `--set`, `--expr`, and `--solve` mean what they mean to a bench.

```bash
eqlens --legend --define '\sigma=the spread' --set '\sigma=1:0.2:3' -o bell.html \
  'f(x) = \frac{1}{\sigma\sqrt{2\pi}} e^{-\frac{(x-\mu)^2}{2\sigma^2}}'
```

A symbol that only takes whole numbers, such as a level `n`, gets a step after its range: `--set 'n=0:0:10/1'`. Its card then draws a dot for each value and no line between, and a bench steps its slider the same way.

`--no-plot` keeps the words and leaves the plot out: use it for a formula of matrices or tensors, which reads as arithmetic but is not a curve. `--no-pop` leaves the cards out. The card's colors follow `--eq-pop-bg`, `--eq-pop-line`, `--eq-fg`, and `--eq-dim` if the page sets them.

The fragment carries its own style and its scripts. The SVG and PNG have no script in them. In an SVG or PNG the tiers are always open.

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

## The bench

`--bench FILE` writes the formula as something to work by hand. The file's ending picks the kind, and you can repeat the flag:

| Ending | What you get | Needs |
|---|---|---|
| `.html` | one page, no outside scripts: the drawing, sliders, a plot, a small plot per symbol | nothing more |
| `.xlsx` | a workbook with live formulas and charts | `pip install 'eqlens[bench]'` |
| `.py` | a ManimGX scene, class `Bench` | ManimGX, to render it |
| `.json` | the spec, to keep | nothing more |

Nothing is drawn unless you also give `-o`.

```bash
eqlens --bench gas.html --solve T --constant R 'PV=nRT'
```

**What is read as written.** Arithmetic, powers, fractions, roots, `\exp`, `\ln`, `\log_{10}`, the trigonometric and hyperbolic functions, and absolute values. `a/bc` is a over bc, as it is in print. `f(x)=...` gives `f` and puts `x` along the bottom of the plot. When neither side is one symbol, as in `PV=nRT`, the formula is solved for the first symbol that can be got alone; `--solve KEY` picks another, and also turns a formula round (`\lambda=h/p` for `p`). Roots and logs take the principal value.

**What is not.** A derivative, an integral, a sum, a matrix, a bra-ket, an inequality, or a function the formula does not define. Two things that could be read two ways are refused too: a bare `\log` (write `\ln` or `\log_{10}`), and an `i`, which may be the imaginary unit (`--set 'i=2:1:5'` says it is a number). eqlens says which, exits 1, and writes nothing. Give one case with `--expr`:

```bash
eqlens --bench box.html \
  --expr 'E = n**2*pi**2*hbar**2/(2*m*L**2)' \
  --set 'n=1:1:5' --set 'L=1:0.5:3' --set 'm=1:0.5:2' \
  -- '-\frac{\hbar^2}{2m}\nabla^2\psi+V\psi=E\psi'
```

In `--expr` each symbol goes under its plain name: `sigma` for `\sigma`, `k_B` for `k_B`, `alpha_bar_t` for `\bar{\alpha}_t`, `x_hat` for `\hat{x}`. It may hold numbers, `+ - * / **`, `pi`, `e`, and `sqrt exp ln log10 sin cos tan asin acos atan sinh cosh tanh abs`. Nothing in it is run as code. A name that is not in the formula must be given a number with `--set`, and the bench is then marked as one case. Where the formula can be read as written, the expression is checked against it at some thirty points, and a wrong one is refused.

**Numbers and ranges.** `--set 'KEY=value'`, `--set 'KEY=value:min:max'`, or `--set 'KEY=value:min:max:unit'`. Without one a symbol starts at 1. `--sweep KEY` picks the symbol along the bottom of the plot. `--constant c` (and the rest of the table) holds a constant at its real SI value: it gets no slider.

**With Claude.** `--introspect --bench FILE` asks Claude for the meanings, and also for the expression, the case when one is needed, and a sensible number and range for each symbol. That is a second request. Your own `--expr` and `--set` win. Add `--bench FILE.json` to keep the answer.

**The workbook.** Change a colored cell on the Bench sheet and the result and every chart follow. The Sweeps sheet holds the numbers the charts draw. The Check sheet works the formula out at eight fixed points beside the answers eqlens got: its top cell reads "agree at 8 points". The file holds formulas and not their answers, so a viewer that does not calculate (a file preview, pandas) shows empty cells. Excel, LibreOffice, Numbers, and Google Sheets calculate when they open it. There are no slider controls in the sheet: openpyxl cannot write them, and the page has them.

**From Python.**

```python
from eqlens.bench import build, make
spec = build(r"E_k=\frac{1}{2}mv^2", sets=["m=2:1:10:kg", "v=3:0:10:m/s"])
make(spec, "kinetic.html")
```

## MCP

`eqlens-mcp` speaks MCP over stdio and needs nothing beyond eqlens itself. `eqlens-mcp --tools` lists the tools.

```bash
claude mcp add --scope user eqlens -- eqlens-mcp       # Claude Code, every project
```

For Claude Desktop or another client, the entry is `{"mcpServers": {"eqlens": {"command": "eqlens-mcp"}}}`.

| Tool | What it does |
|---|---|
| `eqlens_render` | Draws a formula as PNG, SVG, or HTML. Returns the path, and the picture for a PNG. |
| `eqlens_inspect` | Lists the symbols, says whether the formula works out as written, and gives each symbol's plain name. |
| `eqlens_bench` | Writes the page, the workbook, the scene, and the spec. Default: the page and the workbook, in a temporary folder; `out_dir` says where to keep them. |

The server asks no model and needs no key. When a formula cannot be read as written, `eqlens_bench` answers with the reason, and the model calls again with `expr` and `symbols` for one case.

## A terminal that cannot paint a picture

GNOME Terminal and most Linux consoles show text only. There the formula is drawn in braille dots, two across and four down in each character, and each symbol keeps its ledger color. The ledger and the notes are plain lines under it.

```bash
eqlens --legend 'e^{i\pi}+1=0'                    # the dots, then the path of the SVG it wrote
eqlens --display text --legend 'e^{i\pi}+1=0'     # the dots alone, in any terminal
eqlens --display text --columns 60 'E=mc^2'       # no wider than 60 characters
eqlens --display cells 'E=mc^2'                   # the same drawing as JSON, for a program
```

Plain ink is left in the terminal's own text color, so it reads on a light theme and a dark one. A long formula is drawn smaller to fit the width, and past a point small is hard to read: widen the window, or open the file. `NO_COLOR` turns the colors off. Tiers are not drawn in dots.

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
| `--format svg\|png\|html` | Choose the format whatever the file is called. `html` adds the Copy and Expand buttons and a card under each symbol |
| `--no-pop` | `html` only: leave out the card that opens under a symbol |
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
