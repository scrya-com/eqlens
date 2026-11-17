---
name: eqlens
description: >
  Draw a TeX-style math formula as an SVG (default) or PNG, with colored
  symbols, a ledger that says how each symbol is read, and hover highlights. Shows
  it inline with the iTerm2 imgcat protocol (also WezTerm) or Kitty, or writes
  a file on Ubuntu and other terminals. Use when the user asks to show,
  typeset, or display a formula, equation, LaTeX, or math in the terminal or
  for a web page, or runs /eqlens. In Claude Code the plugin shows a PNG in a
  pane. When Greek letters, accents, subscripts, or superscripts appear, use
  --legend. Use --define to say what a symbol means in this formula. May add
  brief intuitive --note lines in fine print. Use the eqlens tools, not an
  image generator and not a full TeX install. Formerly mathcat.
---

# eqlens

Show the formula with `eqlens`. Do not send it through an image generator. Do not install TeX. The README is only the install page. Human usage is `USAGE.md`; follow this skill, not that file.

## Claude Code pane

If the tool `mcp__eqlens__show` is available, call it and do not also run the shell. `tex` is one formula. Set `legend` true under the Legend rules. `defines` is a list of `KEY=meaning` under the Define rules. `notes` is the fine print, under the Notes rules. The pane keeps the PNG path. The terminal draws the file.

The person can type the same thing:

```
/eqlens --legend 'e^{i\pi}+1=0'
/eqlens --define 'P=what one token can carry' 'u^\star=P\,\epsilon-x_0'
/eqlens drop
```

`/eqlens` alone opens the pane. A captured tool shell has no such tool: follow Show it.

## Show it

1. If stdout is the user's iTerm2, WezTerm, or Kitty, run `eqlens '<tex>'`. It draws a PNG inline: a terminal cannot paint an SVG.
2. If stdout is a captured tool shell, do not run bare `eqlens`. It writes the SVG text into the capture. Run `eqlens -o <path>.svg '<tex>'`, or `-o <path>.png` when the user will look at it in a terminal. It prints the absolute path. For a PNG give the user `! imgcat <absolute path>`; for an SVG tell them the full path to open in a browser. Always the full path, starting at `/`. Never shorten it, use `~`, or give a relative path or a bare filename.
3. On a terminal with no inline images (Ubuntu GNOME Terminal and most Linux consoles), `eqlens '<tex>'` writes an SVG and prints its path. Tell the user the full absolute path.
4. If `eqlens` is missing: `python3 -m pip install matplotlib` and `python3 -m pip install "git+https://github.com/scrya-com/eqlens.git"`. From a checkout, `python3 -m pip install .` Then `eqlens` is on `PATH` (often `~/.local/bin`). `mathcat` still works as an old name for the same command.

One formula per call. `$...$` wrappers are optional.

## SVG or PNG

SVG is the default for a file and for a pipe. `-o name.png` or `--format png` gives a PNG. Both are the same picture.

For a web page, write the SVG (or the `.html` fragment, which adds Copy and Expand buttons) and put it inline in the HTML, not in `<img>`. Inline, pointing at a symbol lights every place it appears and its ledger row. There is no tooltip unless you pass `--tips`; leave it off, the row already says it. Inside `<img>` the same file is a still picture. An SVG card carries a small eqlens mark in its corner that links to scrya.com/eqlens; leave it on unless the user asks for `--no-credit`. The page can restyle an inline SVG with the CSS variables `--eq-fg`, `--eq-bg`, `--eq-dim`, and `--eq-mark`.

## Legend

When the formula contains Greek commands (`\pi`, `\alpha`, `\sigma`, and the rest of the mathtext Greek set), accents (`\hat`, `\bar`, `\tilde`, `\vec`, `\dot`, `\ddot`), subscripts, or superscripts, pass `--legend` unless the user asked for the formula alone.

```bash
eqlens --legend -o euler.svg 'e^{i\pi}+1=0'
```

Each Greek letter is colored in the formula and listed once under it, in the order it appears, with its English name in the same color. A letter keeps its color in every formula. A variant uses a spoken name such as "curly phi" or "final sigma". A capital shares the color of its small letter. Named symbols that are not Greek follow, with what they are: "h bar", "del", "partial", "expectation", "indicator", "elementwise product".

After those, each accent and script is read aloud once: "x hat", "y bar", "x sub i", "c squared", "A inverse", "e to the iπ", "∫ from 0", "∫ to 1", "lim as n→∞", "u star", "A transpose", "U dagger", "s prime". A mark that is a convention and not arithmetic also gets one dim line under its name saying what it usually means, such as "A marked u: often the best one, or its complex conjugate. Not a power." Each kind is explained once. `A_e^\top` is one row, "A sub e transpose". A subscript that is already a word, as in `N_{\mathrm{dense}}`, gets no row. Do not repeat these lines in a `--note`. The map is `src/eqlens/legend.py`. Leave the colors there.

`--brief` is `--legend` without the plain subscripts and powers ("x sub 0", "c squared"). Rows with a meaning stay. Use it for a web page or a long formula, where the full ledger would be taller than the formula deserves.

Do not write `\color` in the formula: mathtext rejects it. eqlens colors the glyphs itself. Skip `--legend` when there is no Greek, accent, or script; the flag then changes nothing.

## Define

`--define 'KEY=meaning'` says what a symbol means in this formula. Repeat it. The symbol gets a color in the formula, and a ledger row with the meaning. Use it for the two to five symbols the reader has to know to follow the formula, Latin ones included.

```bash
eqlens --legend \
  --define 'P=keeps the part of the noise the cell can see' \
  --define 'A_e=squeezes a cell of fine tokens into one' \
  --define 'u^\star=the target the model is trained on' \
  'u^\star=P\,\epsilon-x_0,\qquad P=A_eA_e^\top'
```

`KEY` is TeX for the symbol exactly as it appears: `P`, `A_e`, `\epsilon`, `u^\star`, `f_\uparrow`. A key that the ledger already lists keeps its spoken name and takes your meaning in place of the generic line. The meaning is a short phrase, under about 60 characters, lower case, no full stop: what the thing does here, not what it is called. `$...$` inside it draws as math.

When the symbol is a constant with a known value, put the value and its unit after a comma: `--define 'c=the speed of light, $299\,792\,458$ m/s'`, `--define '\Lambda=the cosmological constant, about $1.1\times10^{-52}\,\mathrm{m}^{-2}$'`. Say "about" when it is measured and not exact. Give a value only when you are sure of it; a wrong number is worse than none. `--define` works without `--legend`; then only the defined symbols are listed.

Prefer `--define` to a `--note` when the sentence is about one symbol.

## Tiers

`--tier 'KEY=formula'` says what a symbol is made of. `KEY = formula` is drawn under that symbol's row, with its own rows, and a symbol in there can have a tier too (four deep at most).

```bash
eqlens --brief \
  --define 'P=keeps the coarse part' \
  --tier 'P=A_eA_e^\top' \
  --tier 'A_e=VU^\top' \
  'v=P\,u_a+\frac{(I-P)\,(x_t+u_a)}{\sigma}'
```

Add a tier when a symbol stands for a formula the reader would want to see: one the user's files state, or the standard definition. Do not invent one, and do not restate the formula you started from. One or two tiers per formula is usually right; a tree that is taller than it is useful helps nobody. Give `formula` as the right-hand side only: `P=A_eA_e^\top`, not `P=P=A_eA_e^\top`.

A `--define` reaches a symbol inside a tier, so define the new symbols a tier brings in. In the pane tool, tiers go in `tiers`.

For a web page write `-o name.html`. That is a fragment with a Copy button and, when there are tiers, an Expand button: the tiers start shut. In an SVG or PNG they are always open.

## Look inside

You are the model, so do the looking yourself. Do not run `--introspect`: it calls the Claude API on the user's key to do what you can do here for nothing.

1. Run `eqlens --inspect '<tex>'`. It prints JSON and draws nothing: each symbol and sub-expression, how it is said, and how often it appears. No key, no network.
2. Decide what the formula is and which three to six parts a reader must know. Prefer a whole sub-expression to its pieces: explain `G_{\mu\nu}`, not `\mu` and `\nu`.
3. Draw it with one `--define` per part, copying each `key` from the JSON, and `--brief`. Add one `--note` with the idea of the whole formula.
4. To go a level down, add a `--tier` for a part and run `--inspect` again with the same flags. The JSON is now a tree: that part carries `"tier"`, with the new formula and the symbols it brings in. Define those, and repeat while a level still earns its place.

Use what the user and their files say the symbols mean before the textbook meaning. If you cannot tell what a part means, leave it out.

`--introspect` is for a person at a shell with no model to hand. It needs `pip install 'eqlens[ai]'` and `ANTHROPIC_API_KEY`. `--introspect --inspect` prints the meanings and tiers as JSON to keep.

## Notes

You may add brief intuitive notes in fine print under the formula with `--note`, one flag per line. They are small and dim, under the ledger. Use them for the idea behind the whole formula, not for one symbol and not for names.

```bash
eqlens --legend \
  --note 'Q chooses where to look.' \
  --note 'K says where things are.' \
  --note '$V(f_r)$ is the reference still.' \
  --note 'An empty hand in $f_r$ stays an empty hand.' \
  '\mathrm{Attn}(f_q,f_r)=\mathrm{softmax}\left(\frac{Q(f_q)K(f_r)^T}{\sqrt{d}}\right)V(f_r)'
```

Each note is one plain sentence, under about 60 characters, saying what a part does, not what it is called. Two to four notes at most. No restating the ledger, no equations in prose, no hedging. Put symbols between `$...$` so they render as math. Skip notes when the formula speaks for itself or the user asked for the formula alone.

## A bench: let the user work the formula

When the user wants to explore, play with, plot, animate, or put a formula in a spreadsheet, build a bench. If the `eqlens_bench` MCP tool is there, call it. Otherwise use `--bench`:

```bash
eqlens --bench out/bell.html --bench out/bell.xlsx \
  --define '\mu=the center of the bell' --define '\sigma=how wide the bell is' \
  --set 'x=0:-4:4' --set '\mu=0:-2:2' --set '\sigma=1:0.3:3' \
  'f(x)=\frac{1}{\sigma\sqrt{2\pi}}\exp\left(-\frac{(x-\mu)^{2}}{2\sigma^{2}}\right)'
```

`.html` is a page with sliders, `.xlsx` a workbook (needs `pip install 'eqlens[bench]'`), `.py` a ManimGX scene to render with `manimgx render FILE.py Bench`, `.json` the spec. Each prints its full path.

Always give every symbol a number, a range worth exploring, and a unit: `--set 'KEY=value:min:max:unit'`, or `symbols` in the tool call. Without them every symbol starts at 1. Use `--constant` for physical constants, so they hold their real values. Give `--define` meanings as you would for a drawing.

A non-zero exit that names a derivative, an integral, a sum, a matrix, or an undefined function means the formula cannot be worked out as written. Do not rewrite the formula. Give one standard case with `--expr 'OUT = expression'`, in plain names (`sigma`, `k_B`, `alpha_bar_t`, `x_hat`), with a `--set` for every new name the case brings, and tell the user which case you chose. `--solve KEY` turns a formula round. If eqlens says the expression does not give what the formula says, the expression is wrong: fix it, do not drop the check.

## Dialect

These work: fractions, roots, integrals, sums, subscripts, superscripts, accents, `\left` and `\right`, `\mathrm`, `\mathbb`, `\mathcal`, `\text`, `\hbar`, `\nabla`, `\partial`, `\langle` and `\rangle`, and the Greek commands above.

```text
e^{i\pi}+1=0
x=\frac{-b\pm\sqrt{b^{2}-4ac}}{2a}
i\hbar\frac{\partial}{\partial t}\Psi=\hat{H}\Psi
\theta_{t+1}=\theta_t-\eta\nabla_\theta L(\theta_t)
```

`tests/equations.py` holds some fifty physics, quantum, and machine-learning formulas that are known to draw.

These do not: `\begin{...}` environments, `\usepackage`, `\newcommand`, `\color`, TikZ, `\ce{}`, more than one formula in one call. A non-zero exit means the formula is outside this dialect. Simplify it to one line. Do not redraw it with an image model.

`--font` picks the typeface: `sans` (default), `serif`, `stix`, or `cm`. `stix` and `cm` look like a printed paper.

## More than one formula

Start `eqlensd` once. It listens on `http://127.0.0.1:8765`. Later `eqlens` calls use it. Leave the bind address on localhost.

`POST /svg` or `POST /png` with `{"tex":"...","legend":true,"define":["P=meaning"],"notes":["..."]}` returns `image/svg+xml` or `image/png`. In JSON a backslash is `\\`. Prefer POST. A raw `+` in a query string is a space. `GET /health` returns `{"ok":true,"service":"eqlensd"}`.

`eqlens --local` renders in-process and ignores `eqlensd`. `--note` and `--define` work with or without `--legend`. `-o file` writes a file, prints its absolute path, and does not display it.
