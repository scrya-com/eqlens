<p align="center">
  English · <a href="README.ja.md">日本語</a>
</p>

<p align="center">
  <img src="docs/hero.jpg" alt="Pixel-art thriller: a laptop in the rain, a ribbon of light, and quantum formulas across the frame" width="100%">
</p>

<h1 align="center">eqlens</h1>

<p align="center">
  One math formula, drawn as an SVG or a PNG.<br>
  Every symbol colored, named the way you say it, and lit up with its meaning when you point at it.<br>
  On a web page a card opens under the symbol, with a moving plot of what it alone does to the result.<br>
  Then a bench to work it by hand: a page with sliders, a workbook, and an animation, in the same colors.<br>
  It reads the formula aloud, draws it as a shader, and serves agents over MCP.<br>
  In a plain terminal it draws the formula in braille dots, and burns those dots into a source file as a comment.<br>
  macOS and Ubuntu. No TeX install.
</p>

<p align="center">
  <a href="https://scrya.com/eqlens">Try it in a browser: scrya.com/eqlens</a>
</p>

## Install

Python 3.10 or newer.

```bash
python3 -m pip install matplotlib
python3 -m pip install git+https://github.com/scrya-com/eqlens.git
eqlens 'e^{i\pi}+1=0'
```

`eqlens` lands on your `PATH`, usually at `~/.local/bin`. iTerm2, WezTerm, and Kitty show the picture inline. Anywhere else you get an SVG:

```bash
eqlens -o euler.svg 'e^{i\pi}+1=0'
eqlens -o euler.png 'e^{i\pi}+1=0'
```

<p align="center">
  <img src="docs/euler.png" alt="Euler's identity" width="280">
</p>

## Name the symbols

`--legend` colors each Greek letter and lists it under the formula with its English name. Accents and scripts are read the way people say them: "ψ hat", "∫ from −∞", "u star", "A transpose". A mark that is not a power says so.

```bash
eqlens --legend '\psi(x)=\int_{-\infty}^{\infty}\hat{\psi}(\xi)\,e^{2\pi i x \xi}\,d\xi'
```

<p align="center">
  <img src="docs/legend.png" alt="A Fourier integral with psi, xi, and pi colored in the formula and named in a ledger, then the integral limits, psi hat, and the exponent" width="640">
</p>

## Say what they mean

`--define` gives a symbol its meaning in this formula. It gets a color and a row.

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

`--note` adds a short line in fine print under the ledger. Repeat it for another line. `$...$` inside a note draws as math.

```bash
eqlens --legend \
  --note '$\mu$ is the center of the bell.' \
  --note '$\sigma$ is how wide the bell is.' \
  'f(x)=\frac{1}{\sigma\sqrt{2\pi}}\exp\left(-\frac{(x-\mu)^{2}}{2\sigma^{2}}\right)'
```

<p align="center">
  <img src="docs/note.png" alt="A Gaussian with sigma, pi, and mu colored, a ledger, and two short notes under it" width="640">
</p>

## Open a symbol up

`--tier` says what a symbol is made of. Its formula is drawn under its row, and a symbol in there can open again.

```bash
eqlens --brief \
  --define 'P=keeps the coarse part' \
  --tier 'P=A_eA_e^\top' --tier 'A_e=VU^\top' \
  -o recover.html 'v=P\,u_a+\frac{(I-P)\,(x_t+u_a)}{\sigma}'
```

<p align="center">
  <img src="docs/tier.png" alt="A formula whose P opens into P equals A sub e times A sub e transpose, and whose A sub e opens again into V U transpose" width="640">
</p>

An `.html` output is a fragment for a web page with three glyph buttons: **Read** opens the whole formula in words beside the drawing, with a speaker to hear it; **Expand** opens the tiers; and **Copy** puts the TeX on the clipboard. `eqlens --read` prints the same words. Point at a symbol in the fragment and a card opens underneath: what the symbol means and, when the formula can be worked out, a small moving plot of the result as that symbol alone changes. It works for any formula; nothing is drawn by hand.

## Or draw it with a shader

Name the output `.glsl` or `.frag`, or pass `--format glsl`, for a WebGL2 fragment shader that draws the formula, ledger and all, sharp at any size. Pointing at a symbol (`iMouse`) lights it as in the SVG, and the `mainImage` inside pastes straight into Shadertoy.

```bash
eqlens --legend -o euler.frag 'e^{i\pi}+1=0'
```

[See it running](https://claude.ai/artifact/Q6151o5gGRHZBegqGHh2sV): the equations of the TokenStream paper, each drawn by its own shader. [USAGE.md](USAGE.md#shader-glsl-for-webgl2-and-shadertoy) says how to run it.

## Work it by hand

`--bench` turns a formula into something you can change and watch. Every symbol keeps the color it has on the card.

```bash
python3 -m pip install 'eqlens[bench]'
eqlens --bench bell.html --bench bell.xlsx --bench bell.py \
  --define '\mu=the center of the bell' --define '\sigma=how wide the bell is' \
  --set 'x=0:-4:4' --set '\mu=0:-2:2' --set '\sigma=1:0.3:3' \
  'f(x)=\frac{1}{\sigma\sqrt{2\pi}}\exp\left(-\frac{(x-\mu)^{2}}{2\sigma^{2}}\right)'
```

<p align="center">
  <img src="docs/bench.png" alt="The bell curve with a slider for sigma, x, and mu in their ledger colors, a plot that follows them, and a small plot beside each slider" width="640">
</p>

- `.html` is a page: the drawing, a slider for each symbol, a plot, and beside each slider a small plot of what that symbol alone does. Point at a symbol and its slider lights up.
- `.xlsx` is a workbook: a colored cell for each symbol, the formula as a live cell formula, a chart for each symbol, and a sheet that checks the formula against eqlens at eight points.
- `.py` is a [ManimGX](https://github.com/academa-labs/manimgx) scene: each symbol crosses its range in turn and the curve follows. `manimgx render bell.py Bench`.
- `.json` is the spec. `eqlens --spec bell.json --bench bell.html` builds from it again.

A real, closed-form formula is read as written. One with a derivative, an integral, a sum, or an operator is not guessed at: eqlens says what it needs, and `--expr` gives one case of it. [USAGE.md](USAGE.md#the-bench) has the rest.

## MCP

`eqlens-mcp` serves eqlens to Claude Code, Claude Desktop, or any MCP client. It needs no API key: the model that calls it says what the symbols mean.

```bash
claude mcp add --scope user eqlens -- eqlens-mcp
```

Four tools: `eqlens_render` draws a formula, `eqlens_comment` burns one into a source file as a comment, `eqlens_inspect` lists what is in one, and `eqlens_bench` writes the page, the workbook, and the scene. Then ask: "build a bench for the ideal gas law".

## Or let Claude say it

`--introspect` asks Claude what the parts of the formula stand for and draws them for you. It needs `pip install 'eqlens[ai]'` and an `ANTHROPIC_API_KEY`.

```bash
eqlens --introspect -o einstein.svg 'G_{\mu\nu}+\Lambda g_{\mu\nu}=\frac{8\pi G}{c^4}T_{\mu\nu}'
```

Add `--inspect` to get the meanings as JSON, so you can keep them and draw again without a key. [USAGE.md](USAGE.md#let-claude-say-what-the-parts-mean) has the rest.

## Point at it

Put the SVG inline in a web page, or open the file in a browser. Point at a symbol: every place it appears lights up with its row, and the rest dims. It is CSS inside the SVG, with no script.

There are twelve formulas to try at [scrya.com/eqlens](https://scrya.com/eqlens). [USAGE.md](USAGE.md#hover) shows how to put one in your own page.

## What it draws

One formula per call, set by matplotlib's mathtext: fractions, roots, integrals, sums, accents, subscripts, superscripts, `\mathrm`, `\mathbb`, `\mathcal`, and Greek. No `\begin{...}` environments and no preamble.

The tests draw some fifty formulas from physics, quantum physics, and machine learning, and check that every symbol in a ledger is found again in its formula: [`tests/equations.py`](tests/equations.py).

## Claude Code

A pane for the formulas, beside the chat. Run Claude Code in [Kitty](https://sw.kovidgoyal.net/kitty/) and the pane shows the real picture: `/eqlens` draws a formula into it, and every formula the agent draws lands there too.

![Claude Code in Kitty: the agent lists seven equations it drew, and the eqlens pane shows one with each symbol colored and explained](docs/kitty-pane.webp)

```bash
sudo apt install kitty        # or: brew install --cask kitty
kitty claude --plugin-dir /path/to/eqlens
```

```
/plugin install eqlens --marketplace scrya-com/eqlens
```

Or load it from a checkout for one session:

```bash
claude --plugin-dir /path/to/eqlens
```

With the eqlens MCP server also connected, the pane follows it: each PNG that `eqlens_render` draws shows in the pane too.

```
/eqlens
/eqlens e^{i\pi}+1=0
/eqlens --legend 'e^{i\pi}+1=0'
/eqlens drop
```

`/eqlens` opens the pane. A formula is drawn and kept. Prev, Next, and Drop walk that list. `--legend`, `--define`, and `--note` are the same flags as the command line.

Kitty paints the PNG, and so do Ghostty and iTerm2, with Claude Code 2.1.287 or later. Any other terminal, GNOME Terminal among them, gets the formula in braille dots with the ledger in words under it. A narrow window holds the pane back until you type `/eqlens`.

## For an LLM

Do not invent a workflow from this page. Load the eqlens skill and follow it.

- Grok: [`.grok/skills/eqlens/SKILL.md`](.grok/skills/eqlens/SKILL.md)
- Claude: [`.claude/skills/eqlens/SKILL.md`](.claude/skills/eqlens/SKILL.md)

They are the same file. Install both so a chat in either tool can run it:

```bash
mkdir -p ~/.grok/skills ~/.claude/skills
ln -sfn /path/to/eqlens/.grok/skills/eqlens ~/.grok/skills/eqlens
ln -sfn /path/to/eqlens/.grok/skills/eqlens ~/.claude/skills/eqlens
```

Asking to see a formula selects the skill. With the pane installed, `/eqlens` draws into it.

People who want the flags, fonts, hover, the server, and the Python calls: [USAGE.md](USAGE.md).

## It used to be mathcat

eqlens was `johndpope/mathcat` before 0.2. The old address redirects here, and the `mathcat` command still runs.

## License

Copyright 2026 John D. Pope.

[Do No Harm License](LICENSE.md) (pre 1.0), the license at [raisely/NoHarm](https://github.com/raisely/NoHarm/blob/publish/LICENSE.md).
