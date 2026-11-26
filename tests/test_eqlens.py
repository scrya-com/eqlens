import contextlib
import importlib.util
import io
import json
import os
import re
import struct
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from xml.etree import ElementTree


from equations import ALL, ML, PHYSICS, QUANTUM

from eqlens.cli import main
from eqlens.display import display_png
from eqlens.engine import layout
from eqlens.introspect import IntrospectError, inspect, introspect
from eqlens.legend import MAX_TIERS, greek_in, hints_in, named_in, notation_in, occurrences, plain, plan, symbols
from eqlens.render import FormulaError, render_glsl, render_html, render_png, render_svg
from eqlens.server import Handler
from eqlens.speech import read, say
from html import escape as html_escape


def _size(png: bytes) -> tuple[int, int]:
    return struct.unpack(">II", png[16:24])


class RenderTests(unittest.TestCase):
    def test_euler_is_png(self):
        png = render_png(r"e^{i\pi}+1=0")
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_dollars_are_optional(self):
        bare = render_png(r"E=mc^2")
        wrapped = render_png(r"$E=mc^2$")
        self.assertTrue(bare.startswith(b"\x89PNG"))
        self.assertTrue(wrapped.startswith(b"\x89PNG"))

    def test_environment_is_rejected(self):
        with self.assertRaises(FormulaError):
            render_png(r"\begin{matrix}a\end{matrix}")

    def test_empty_is_rejected(self):
        with self.assertRaises(FormulaError):
            render_png("   ")


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.httpd.server_address
        cls.base = f"http://{host}:{port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_health(self):
        with urllib.request.urlopen(self.base + "/health") as response:
            body = json.loads(response.read().decode())
        self.assertEqual(body["ok"], True)

    def test_post_png(self):
        payload = json.dumps({"tex": r"e^{i\pi}+1=0"}).encode()
        request = urllib.request.Request(
            self.base + "/png",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            png = response.read()
            self.assertEqual(response.headers.get("Content-Type"), "image/png")
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_post_svg_with_a_ledger(self):
        payload = json.dumps({"tex": r"e^{i\pi}+1=0", "legend": True, "tips": True, "define": ["e=Euler's number"]}).encode()
        request = urllib.request.Request(
            self.base + "/svg",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            svg = response.read().decode()
            self.assertEqual(response.headers.get("Content-Type"), "image/svg+xml")
        self.assertIn("<title>pi</title>", svg)
        self.assertIn("Euler's number", svg)

    def test_get_svg(self):
        with urllib.request.urlopen(self.base + "/svg?tex=x%5E2&legend=1&note=Hello") as response:
            self.assertTrue(response.read().startswith(b"<svg"))

    def test_bad_formula_is_400(self):
        payload = json.dumps({"tex": r"\begin{align}a\end{align}"}).encode()
        request = urllib.request.Request(
            self.base + "/png",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 400)


class LegendTests(unittest.TestCase):
    def test_order_and_uniqueness(self):
        found = greek_in(r"\alpha+\pi+\alpha+\beta")
        self.assertEqual([item[0] for item in found], ["alpha", "pi", "beta"])
        self.assertEqual([item[2] for item in found], ["alpha", "pi", "beta"])

    def test_same_letter_keeps_its_color(self):
        first = greek_in(r"\pi")[0][3]
        later = greek_in(r"\sigma+\pi")[1][3]
        self.assertEqual(first, later)
        self.assertEqual(greek_in(r"\pi")[0][3], greek_in(r"\Pi")[0][3])

    def test_ledger_is_a_taller_png(self):
        tex = r"e^{i\pi}+1=0"
        card = render_png(tex, legend=True)
        self.assertTrue(card.startswith(b"\x89PNG"))
        self.assertGreater(_size(card)[1], _size(render_png(tex))[1])

    def test_no_notation_leaves_the_formula(self):
        tex = r"E=mc"
        self.assertEqual(render_png(tex, legend=True), render_png(tex))

    def test_scripts_alone_get_a_ledger(self):
        tex = r"E=mc^2"
        self.assertGreater(_size(render_png(tex, legend=True))[1], _size(render_png(tex))[1])

    def test_accents_and_scripts_are_spoken(self):
        spoken = [item[2] for item in notation_in(r"\hat{x}_i^2+\bar{y}+A^{-1}+f(x)^3")]
        self.assertEqual(
            spoken,
            [
                "$x$ hat",
                r"$\hat{x}$ sub $i$",
                r"$\hat{x}_{i}$ squared",
                "$y$ bar",
                "$A$ inverse",
                "$f(x)$ cubed",
            ],
        )

    def test_limits_read_from_and_to(self):
        spoken = [item[2] for item in notation_in(r"\int_{0}^{1} x\,dx + \lim_{n\to\infty} a_n")]
        self.assertEqual(
            spoken,
            [r"$\int$ from $0$", r"$\int$ to $1$", r"$\lim$ as $n\to\infty$", "$a$ sub $n$"],
        )

    def test_notes_alone_make_a_card(self):
        tex = r"E=mc"
        card = render_png(tex, notes=["Mass is energy at rest."])
        self.assertGreater(_size(card)[1], _size(render_png(tex))[1])
        self.assertEqual(render_png(tex, notes=["  "]), render_png(tex))

    def test_note_with_broken_mathtext_still_renders(self):
        tex = r"x_i"
        card = render_png(tex, notes=["costs $5 and $\\frac{"])
        self.assertTrue(card.startswith(b"\x89PNG"))

    def test_notation_is_listed_once(self):
        self.assertEqual(len(notation_in(r"x_i+x_i+x_{i}")), 1)

    def test_star_and_top_are_spoken_not_raised(self):
        spoken = [item[2] for item in notation_in(r"u^\star+v^*+w^{\ast}+A^\top+B^{\mathsf{T}}")]
        self.assertEqual(
            spoken,
            ["$u$ star", "$v$ star", "$w$ star", "$A$ transpose", "$B$ transpose"],
        )

    def test_a_mark_that_is_not_a_power_says_so_once(self):
        hints = hints_in(r"u^\star=x^2+v^\star+\hat{y}")
        self.assertEqual(list(hints), [r"u^{\star}", r"\hat{y}"])
        self.assertIn("Not a power", hints[r"u^{\star}"])
        self.assertIn("$u$", hints[r"u^{\star}"])

    def test_subscript_then_superscript_is_one_thing(self):
        spoken = [item[2] for item in notation_in(r"A_e^\top+\sum_{i}^{n}x")]
        self.assertEqual(
            spoken,
            ["$A$ sub $e$", "$A_{e}$ transpose", r"$\sum$ from $i$", r"$\sum$ to $n$"],
        )

    def test_a_word_subscript_names_itself(self):
        tex = r"N_{\mathrm{LoT}}<N_\mathrm{dense}"
        self.assertEqual(notation_in(tex), [])
        self.assertEqual([item[2] for item in notation_in(r"x_{\mathrm{in}}^2")], [r"$x_{\mathrm{in}}$ squared"])

    def test_a_hint_makes_the_ledger_taller(self):
        tex, same = r"u^\star", r"u^{2}"
        self.assertGreater(_size(render_png(tex, legend=True))[1], _size(render_png(same, legend=True))[1])


class SymbolTests(unittest.TestCase):
    TEX = r"u^\star=P\,\epsilon-x_0,\qquad P=A_eA_e^\top"

    def test_a_symbol_is_found_wherever_it_appears(self):
        formula = layout(f"${self.TEX}$", 22)
        self.assertEqual(len(occurrences(formula, "P")), 2)
        self.assertEqual(len(occurrences(formula, r"\epsilon")), 1)
        self.assertEqual([len(found) for found in occurrences(formula, "A_{e}")], [2, 2])
        self.assertEqual([len(found) for found in occurrences(formula, r"A_{e}^{\top}")], [3])
        self.assertEqual(occurrences(formula, "Q"), [])

    def test_define_gives_a_meaning_a_color_and_a_row(self):
        rows = symbols(self.TEX, define=["P=what one token can carry", r"u^\star=the training target"])
        by_key = {row.key: row for row in rows}
        self.assertEqual(by_key["P"].hint, "what one token can carry")
        self.assertTrue(by_key["P"].color)
        # u^\star is the row the ledger already has, not a second one.
        self.assertEqual(sum(row.name == "$u$ star" for row in rows), 1)
        star = by_key[r"u^{\star}"]
        self.assertEqual(star.hint, "the training target")
        self.assertEqual(star.tip, "u star. the training target")
        self.assertNotEqual(star.color, by_key[r"\epsilon"].color)

    def test_define_alone_lists_only_what_was_defined(self):
        rows = symbols(self.TEX, legend=False, define=["P=what one token can carry"])
        self.assertEqual([row.key for row in rows], ["P"])
        self.assertEqual(rows[0].tip, "P: what one token can carry")

    def test_brief_keeps_only_rows_with_something_to_say(self):
        full = [row.tip.split(".")[0] for row in symbols(self.TEX)]
        brief = [row.tip.split(".")[0] for row in symbols(self.TEX, brief=True)]
        self.assertIn("x sub 0", full)
        self.assertEqual(brief, ["epsilon", "u star", "A_e transpose"])
        kept = symbols(self.TEX, brief=True, define=["x_0=the clean picture"])
        self.assertIn("x sub 0. the clean picture", [row.tip for row in kept])
        self.assertLess(_size(render_png(self.TEX, brief=True))[1], _size(render_png(self.TEX, legend=True))[1])

    def test_bad_define_is_rejected(self):
        for item in ("P", "=meaning", r"\frac{=x"):
            with self.assertRaises(FormulaError):
                render_svg("P=1", define=[item])

    def test_tooltips_are_plain_text(self):
        self.assertEqual(plain(r"$A_{e}$ transpose"), "A_e transpose")
        self.assertEqual(plain(r"$\hat{\psi}$ sub $i$"), "ψ\u0302 sub i")
        self.assertEqual(plain(r"costs \$5"), "costs $5")


class SvgTests(unittest.TestCase):
    TEX = SymbolTests.TEX

    def test_svg_is_one_well_formed_document(self):
        svg = render_svg(self.TEX, legend=True, notes=["A <note> & more."])
        root = ElementTree.fromstring(svg)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertEqual(root.get("aria-label"), self.TEX)

    def test_formula_wears_the_ledger_colors(self):
        color = greek_in(r"\epsilon")[0][3]
        self.assertNotIn(color, render_svg(self.TEX))
        self.assertGreaterEqual(render_svg(self.TEX, legend=True).count(f'fill="{color}"'), 2)

    def test_a_symbol_and_its_row_share_a_class_and_a_tooltip(self):
        svg = render_svg(self.TEX, define=["P=what one token can carry"], tips=True)
        root = ElementTree.fromstring(svg)
        groups = [g for g in root.iter("{http://www.w3.org/2000/svg}g") if "s0" in (g.get("class") or "").split()]
        kinds = sorted((g.get("class") or "").split()[0] for g in groups)
        self.assertEqual(kinds, ["f", "f", "r"])
        for group in groups:
            self.assertEqual(group.find("{http://www.w3.org/2000/svg}title").text, "P: what one token can carry")
        self.assertIn(":has(.s0:hover)", svg)

    def test_there_is_no_tooltip_unless_asked(self):
        svg = render_svg(self.TEX, legend=True, define=["P=what one token can carry"])
        self.assertNotIn("<title>", svg)
        self.assertIn(":has(.s0:hover)", svg)
        self.assertIn("<title>", render_svg(self.TEX, legend=True, tips=True))

    def test_two_formulas_do_not_share_ids(self):
        first = re.search(r'class="(eq[0-9a-f]+)"', render_svg("a+b")).group(1)
        second = re.search(r'class="(eq[0-9a-f]+)"', render_svg("a+c")).group(1)
        self.assertNotEqual(first, second)

    def test_png_and_svg_are_the_same_shape(self):
        root = ElementTree.fromstring(render_svg(self.TEX, legend=True, credit=False))
        _x, _y, width, height = (float(part) for part in root.get("viewBox").split())
        pixels = _size(render_png(self.TEX, legend=True, dpi=144))
        self.assertAlmostEqual(pixels[0] / pixels[1], width / height, places=1)

    def test_every_font_draws(self):
        for font in ("sans", "serif", "stix", "cm"):
            self.assertIn("<use", render_svg(r"\frac{a}{b}+\sum_i x_i", font=font, legend=True))
        with self.assertRaises(FormulaError):
            render_svg("x", font="comic")


class EquationTests(unittest.TestCase):
    """Physics, quantum physics, and machine learning, as people write them."""

    def tips(self, name):
        return [row.tip for row in symbols(dict(ALL)[name])]

    def test_every_equation_draws_as_svg(self):
        for name, tex in ALL:
            with self.subTest(name):
                root = ElementTree.fromstring(render_svg(tex, legend=True))
                self.assertGreater(len(list(root.iter("{http://www.w3.org/2000/svg}use"))), 2)

    def test_one_of_each_field_draws_as_png_in_every_font(self):
        for tex in (PHYSICS[4][1], QUANTUM[0][1], ML[3][1]):
            for font in ("sans", "serif", "stix", "cm"):
                with self.subTest(tex=tex, font=font):
                    self.assertTrue(render_png(tex, legend=True, font=font, dpi=96).startswith(b"\x89PNG"))

    def test_every_ledger_row_is_found_in_its_formula(self):
        for name, tex in ALL:
            formula = layout(f"${tex}$", 22)
            for row in symbols(tex):
                with self.subTest(name, row=row.key):
                    self.assertTrue(occurrences(formula, row.key))

    def test_every_field_is_covered(self):
        self.assertGreaterEqual(len(PHYSICS), 15)
        self.assertGreaterEqual(len(QUANTUM), 15)
        self.assertGreaterEqual(len(ML), 15)
        self.assertEqual(len({name for name, _tex in ALL}), len(ALL))

    def test_physics_readings(self):
        self.assertEqual(self.tips("newton")[0], "F vector. F has a direction as well as a size.")
        self.assertEqual(self.tips("gravitation"), ["m sub 1", "m sub 2", "r squared"])
        self.assertIn("q dot. How fast q changes in time.", self.tips("euler-lagrange"))
        self.assertIn("∇ squared. The Laplacian: how a point differs from the average around it.", self.tips("heat"))
        self.assertIn("G sub μν", self.tips("einstein field"))
        self.assertIn("∮ from ∂S", self.tips("stokes theorem"))
        self.assertEqual(self.tips("ideal gas"), [])

    def test_quantum_readings(self):
        tips = self.tips("schrodinger")
        self.assertEqual(tips[0], "Psi")
        self.assertIn("h bar. Planck's constant divided by 2π, about 1.055×10^-34 J s.", tips)
        self.assertIn("H hat. An estimate of H, or in quantum mechanics an operator.", tips)
        self.assertIn("ℏ squared", self.tips("stationary schrodinger"))
        self.assertEqual(self.tips("unitary"), ["U dagger. U transposed and complex-conjugated. Not a power."])
        self.assertEqual(self.tips("ladder operator")[1].split(".")[0], "a\u0302 dagger")
        self.assertIn("Φ plus", self.tips("bell state"))

    def test_machine_learning_readings(self):
        self.assertIn("K transpose. K with rows and columns swapped. Not a power.", self.tips("attention"))
        ridge = self.tips("ridge regression")
        self.assertEqual(ridge[1].split(".")[0], "w star")
        self.assertIn("(X^TX+λI) inverse. What undoes (X^TX+λI).", ridge)
        self.assertIn("α bar. Often the average of α.", self.tips("diffusion forward"))
        tex = dict(ALL)["diffusion forward"]
        brief = [row.tip for row in symbols(tex, brief=True, define=[r"\bar{\alpha}_t=how much of the picture is left"])]
        self.assertNotIn("α bar. Often the average of α.", brief)
        self.assertIn("α\u0304 sub t. how much of the picture is left", brief)
        self.assertEqual(self.tips("elbo")[0], "expectation. The average over everything that can happen.")
        self.assertIn("∑ from j=1", self.tips("softmax"))
        self.assertIn("max over a'", self.tips("bellman"))
        self.assertIn("s prime. A second s, or its derivative. Not a power.", self.tips("bellman"))
        self.assertIn("norm squared. The length of what is between the bars, squared.", self.tips("flow matching"))

    def test_a_time_index_is_not_a_transpose(self):
        self.assertIn("β_1 to the t", self.tips("adam moment"))
        self.assertEqual([item[2] for item in notation_in(r"2^T")], ["$2$ to the $T$"])


class TierTests(unittest.TestCase):
    TEX = r"v=P\,u_a+\frac{(I-P)\,(x_t+u_a)}{\sigma}"
    TIERS = [r"P=A_eA_e^\top", r"A_e=VU^\top"]

    def test_a_symbol_opens_into_its_formula_and_that_one_opens_again(self):
        top, rows = plan(self.TEX, legend=False, define=["P=keeps the coarse part"], tier=self.TIERS)
        self.assertEqual([rows[index].key for index, _tier in top.rows], ["P"])
        inside = top.rows[0][1]
        self.assertEqual(inside.tex, r"P=A_eA_e^\top")
        self.assertEqual([rows[index].key for index, _tier in inside.rows], ["A_{e}"])
        deeper = inside.rows[0][1]
        self.assertEqual(deeper.tex, r"A_{e}=VU^\top")
        self.assertEqual(deeper.rows, [])

    def test_a_tier_alone_gives_its_symbol_a_row_and_a_color(self):
        top, rows = plan("y=Wx", legend=False, tier=["W=W_0+BA"])
        self.assertEqual([(rows[index].key, rows[index].hint) for index, _tier in top.rows], [("W", "")])
        self.assertTrue(rows[0].color)
        self.assertEqual(top.rows[0][1].tex, "W=W_0+BA")

    def test_a_tier_that_names_itself_opens_once(self):
        top, rows = plan("x=1", legend=False, tier=["x=x+1"])
        inside = top.rows[0][1]
        self.assertEqual(inside.tex, "x=x+1")
        self.assertEqual(inside.rows, [])

    def test_tiers_stop_at_the_depth_limit(self):
        chain = [f"a_{{{i}}}=a_{{{i + 1}}}+1" for i in range(MAX_TIERS + 3)]
        block, _rows = plan("y=a_{0}", legend=False, tier=chain)
        depth = 0
        while block.rows and block.rows[0][1]:
            block = block.rows[0][1]
            depth += 1
        self.assertEqual(depth, MAX_TIERS)

    def test_a_symbol_is_listed_once_and_lights_up_in_every_tier(self):
        svg = render_svg(self.TEX, define=["P=keeps the coarse part"], tier=self.TIERS, credit=False)
        root = ElementTree.fromstring(svg)
        groups = [g.get("class").split() for g in root.iter("{http://www.w3.org/2000/svg}g")]
        # P: twice in the top formula, once in its own tier, and one row.
        self.assertEqual(sorted(g[0] for g in groups if "s0" in g), ["f", "f", "f", "r"])
        # A_e: two glyphs in each of two places in P's tier, two more heading its own, and one row.
        self.assertEqual(sum("s1" in g and g[0] == "r" for g in groups), 1)
        self.assertEqual(sum("s1" in g and g[0] == "f" for g in groups), 6)

    def test_tiers_make_the_card_taller_and_are_in_the_png_too(self):
        plain_card = _size(render_png(self.TEX, define=["P=keeps the coarse part"]))
        tiered = _size(render_png(self.TEX, define=["P=keeps the coarse part"], tier=self.TIERS))
        self.assertGreater(tiered[1], plain_card[1])

    def test_a_definition_reaches_a_symbol_inside_a_tier(self):
        _top, rows = plan(self.TEX, legend=False, define=["A_e=squeezes a cell into one token"], tier=self.TIERS)
        self.assertEqual({row.key: row.hint for row in rows}["A_{e}"], "squeezes a cell into one token")

    def test_h_bar_opens_into_what_it_is_made_of(self):
        tex = dict(ALL)["schrodinger"]
        top, rows = plan(tex, known=True)
        inside = {rows[index].key: tier for index, tier in top.rows}[r"\hbar"]
        self.assertEqual(inside.tex, r"\hbar=\frac{h}{2\pi}")
        self.assertEqual([rows[index].key for index, _tier in inside.rows], [r"\pi"])
        closed, _rows = plan(tex)
        self.assertTrue(all(tier is None for _index, tier in closed.rows))

    def test_the_laplacian_opens_and_a_tier_of_your_own_wins(self):
        top, rows = plan(dict(ALL)["heat"], known=True)
        inside = {rows[index].key: tier for index, tier in top.rows}[r"\nabla^{2}"]
        self.assertIn(r"\partial x^2", inside.tex)
        top, rows = plan(dict(ALL)["schrodinger"], known=True, tier=[r"\hbar=1.054\times 10^{-34}"])
        self.assertEqual({rows[i].key: t for i, t in top.rows}[r"\hbar"].tex, r"\hbar=1.054\times 10^{-34}")

    def test_known_tiers_are_behind_expand_in_html_and_off_in_svg(self):
        tex = dict(ALL)["schrodinger"]
        page = render_html(tex, legend=True)
        self.assertEqual(page.count('class="eqlens-expand"'), 1)
        shut, wide = page.split('<div class="eqlens-open" hidden>')
        self.assertEqual(shut.count('<g class="t">'), 0)
        self.assertEqual(wide.count('<g class="t">'), 1)
        self.assertEqual(render_svg(tex, legend=True).count('<g class="t">'), 0)
        self.assertEqual(render_svg(tex, legend=True, known=True).count('<g class="t">'), 1)
        self.assertNotIn('class="eqlens-expand"', render_html(tex, legend=True, known=False))
        self.assertNotIn('class="eqlens-expand"', render_html("E=mc^2", legend=True))

    def test_what_opens_shows_a_triangle_and_can_be_clicked(self):
        page = render_html(self.TEX, define=["P=keeps the coarse part"], tier=self.TIERS)
        shut, wide = page.split('<div class="eqlens-open" hidden>')
        # Shut: one triangle, on P. Its row and both of its glyphs in the formula can be clicked.
        self.assertEqual(len(re.findall(r'<g class="v s0 h">', shut)), 1)
        self.assertEqual(len(re.findall(r'<g class="r s0 h x">', shut)), 1)
        self.assertEqual(len(re.findall(r'<g class="f s0 h x">', shut)), 2)
        self.assertEqual(len(re.findall(r'<g class="v ', shut)), 1)
        # Open: P and A_e each have a triangle, now for shutting.
        self.assertEqual(len(re.findall(r'<g class="v ', wide)), 2)
        self.assertIn("@media (hover:none)", shut)
        self.assertIn("flip(", page)
        # A drawing on its own has nothing to click.
        alone = render_svg(self.TEX, define=["P=keeps the coarse part"], tier=self.TIERS)
        self.assertNotIn('class="v ', alone)
        self.assertNotIn(" x\"", alone)

    def test_a_letter_is_not_the_bigger_symbol_it_sits_in(self):
        tex = r"G_{\mu\nu}=R_{\mu\nu}-\frac{1}{2}R\,g_{\mu\nu}"
        svg = render_svg(tex, define=[r"R_{\mu\nu}=the Ricci tensor", "R=the Ricci scalar"], credit=False)
        root = ElementTree.fromstring(svg)
        groups = [g.get("class").split() for g in root.iter("{http://www.w3.org/2000/svg}g")]
        # The lone R is one glyph and R_{mu nu} is three: the R inside the tensor is not the scalar.
        self.assertEqual(sum("s0" in g and g[0] == "f" for g in groups), 1)
        self.assertEqual(sum("s1" in g and g[0] == "f" for g in groups), 3)
        self.assertEqual(sum("s0" in g and "s1" in g for g in groups), 0)
        # A_e inside A_e^T is still A_e: the transpose was given no meaning of its own.
        svg = render_svg(r"P=A_eA_e^\top", legend=True, define=["A_e=the squeeze"], credit=False)
        root = ElementTree.fromstring(svg)
        rows = [g.get("class").split() for g in root.iter("{http://www.w3.org/2000/svg}g")]
        both = [g for g in rows if g[0] == "f" and len([c for c in g if c.startswith("s")]) == 2]
        self.assertEqual(len(both), 2)

    def test_a_symbol_in_the_formula_is_listed_there_not_inside_a_tier(self):
        tex = r"G_{\mu\nu}+\Lambda g_{\mu\nu}=0"
        top, rows = plan(tex, legend=False, define=[r"g_{\mu\nu}=the metric"], tier=[r"G_{\mu\nu}=R_{\mu\nu}-\frac{1}{2}R\,g_{\mu\nu}"])
        self.assertEqual(sorted(rows[index].key for index, _tier in top.rows), [r"G_{\mu\nu}", r"g_{\mu\nu}"])

    def test_a_constant_can_carry_its_value(self):
        meaning = r"\Lambda=the cosmological constant, about $1.1\times10^{-52}\,\mathrm{m}^{-2}$"
        row = symbols(r"\Lambda g", legend=False, define=[meaning])[0]
        self.assertEqual(row.tip, "Lambda. the cosmological constant, about 1.1×10^-52 m^-2")
        self.assertTrue(render_svg(r"\Lambda g", define=[meaning]))
        self.assertIn("1.055", dict((key, hint) for key, _name, hint in named_in(r"\hbar"))[r"\hbar"])

    def test_the_triangle_never_shares_a_class_with_the_fine_print(self):
        # The fine print is filled through class "d". A rule that hides the triangle must not reach it.
        page = render_html(dict(ALL)["schrodinger"], legend=True, define=[r"\Psi=the wave function"])
        self.assertIn(' class="d"/>', page)
        hidden = re.findall(r"\.eq[0-9a-f]+ \.(\w+)\{opacity:0", page)
        self.assertEqual(set(hidden), {"v"})
        self.assertNotIn(' class="v"', page)

    def test_bad_tiers_are_rejected(self):
        for item in ("P", "=x", r"P=\frac{", r"\frac{=x"):
            with self.assertRaises(FormulaError):
                render_svg(self.TEX, tier=[item])

    def test_inspect_shows_the_tiers_as_a_tree(self):
        found = inspect(self.TEX, tier=self.TIERS)
        row = next(row for row in found["symbols"] if row["key"] == "P")
        self.assertEqual(row["tier"]["tex"], r"P=A_eA_e^\top")
        deeper = next(r for r in row["tier"]["symbols"] if r["key"] == "A_{e}")
        self.assertEqual(deeper["tier"]["tex"], r"A_{e}=VU^\top")
        self.assertEqual(deeper["appears"], 2)

    def test_the_command_line_takes_tiers(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--inspect", "--tier", r"P=A_eA_e^\top", self.TEX]), 0)
        found = json.loads(out.getvalue())
        self.assertIn("tier", next(row for row in found["symbols"] if row["key"] == "P"))


class CreditTests(unittest.TestCase):
    def test_a_card_links_back_and_a_bare_formula_does_not(self):
        card = render_svg(r"e^{i\pi}+1=0", legend=True)
        root = ElementTree.fromstring(card)
        links = list(root.iter("{http://www.w3.org/2000/svg}a"))
        self.assertEqual([link.get("href") for link in links], ["https://scrya.com/eqlens"])
        self.assertEqual(links[0].get("target"), "_blank")
        image = links[0].find("{http://www.w3.org/2000/svg}image")
        self.assertEqual(float(image.get("width")) * 4 / 3, 30.0)
        self.assertTrue(image.get("href").startswith("data:image/png;base64,"))
        self.assertNotIn("<a ", render_svg("a+b"))

    def test_the_mark_fetches_nothing_and_can_be_left_off(self):
        card = render_svg(r"e^{i\pi}+1=0", legend=True)
        elsewhere = re.sub(r"http://www\.w3\.org/\S*|https://scrya\.com/eqlens", "", card)
        self.assertNotIn("http", elsewhere)
        self.assertNotIn("<image", render_svg(r"e^{i\pi}+1=0", legend=True, credit=False))
        self.assertEqual(render_png(r"e^{i\pi}+1=0", legend=True), render_png(r"e^{i\pi}+1=0", legend=True, credit=False))

    def test_the_mark_sits_clear_of_the_last_line(self):
        with_mark = ElementTree.fromstring(render_svg(r"e^{i\pi}+1=0", legend=True))
        without = ElementTree.fromstring(render_svg(r"e^{i\pi}+1=0", legend=True, credit=False))
        height = lambda root: float(root.get("viewBox").split()[3])
        self.assertGreater(height(with_mark), height(without))


class HtmlTests(unittest.TestCase):
    TEX = TierTests.TEX

    def test_a_fragment_has_a_copy_button_and_the_tex_to_copy(self):
        page = render_html(r"a<b & c", legend=True)
        self.assertIn('data-tex="a&lt;b &amp; c"', page)
        self.assertEqual(page.count('class="eqlens-copy"'), 1)
        self.assertNotIn('class="eqlens-expand"', page)
        self.assertEqual(page.count("<svg xmlns"), 1)

    def test_tiers_add_an_expand_button_and_a_second_drawing(self):
        page = render_html(self.TEX, define=["P=keeps the coarse part"], tier=TierTests.TIERS)
        self.assertEqual(page.count('class="eqlens-expand"'), 1)
        self.assertEqual(page.count("<svg xmlns"), 2)
        shut, wide = page.split('<div class="eqlens-open" hidden>')
        self.assertNotIn(r"VU", shut.split("data-tex")[0])
        height = lambda text: float(re.search(r'viewBox="0 0 [\d.]+ ([\d.]+)"', text).group(1))
        self.assertGreater(height(wide), height(shut))
        ids = re.findall(r'<svg [^>]*class="(eq[0-9a-f]+)"', page)
        self.assertEqual(len(set(ids)), 2)

    def test_the_file_name_picks_html(self):
        path = os.path.join(self.id().replace(".", "_") + ".html")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--local", "--legend", "-o", path, r"E=mc^2"]), 0)
            with open(path, encoding="utf-8") as handle:
                self.assertTrue(handle.read().startswith('<figure class="eqlens"'))
        finally:
            if os.path.exists(path):
                os.remove(path)


class ReadTests(unittest.TestCase):
    LOSS = (
        r"L = \frac{\|(1-M)\odot(\hat{v}^{l}-v^{l})\|^{2}}{\|1-M\|_{1}}"
        r" + \frac{\|M_\uparrow\odot(\hat{v}^{h}-v^{h})\|^{2}}{\|M_\uparrow\|_{1}}"
    )

    def test_a_loss_reads_in_phrases(self):
        self.assertEqual(
            read(self.LOSS).splitlines(),
            [
                "L equals",
                "the squared L2 norm of (1 minus M) elementwise times (v hat l minus v l)",
                "over the L1 norm of (1 minus M)",
                "plus",
                "the squared L2 norm of M up arrow elementwise times (v hat h minus v h)",
                "over the L1 norm of M up arrow",
            ],
        )
        self.assertNotIn("\n", say(self.LOSS))

    def test_readings_people_use(self):
        cases = {
            r"e^{i\pi}+1=0": "e to the i pi plus 1 equals 0",
            r"x=\frac{-b\pm\sqrt{b^{2}-4ac}}{2a}": "x equals (minus b plus or minus the square root of (b squared minus 4 a c)) over 2 a",
            r"E_k=\frac{1}{2}mv^2": "E sub k equals one half m v squared",
            r"\frac{\partial^2 u}{\partial t^2}=c^2\nabla^2u": "the second partial derivative of u with respect to t equals c squared del squared u",
            r"\nabla\cdot\vec{E}=0": "del dot E vector equals 0",
            r"P(A|B)=\frac{P(B|A)P(A)}{P(B)}": "P of A given B equals P of B given A P of A over P of B",
            r"P(x)=|\psi(x)|^2": "P of x equals the squared absolute value of psi of x",
            r"\langle\psi|\hat{A}|\psi\rangle": "the matrix element of A hat between psi and psi",
            r"\hat{a}^\dagger|n\rangle": "a hat dagger ket n",
            r"D_{KL}(P\|Q)": "D sub K L, (P parallel Q)",
            r"\sum_{i=1}^{n} x_i^2": "the sum from i equals 1 to n of x sub i squared",
            r"\lim_{n\to\infty} a_n": "the limit as n goes to infinity of a sub n",
            r"A_e^\top": "A sub e transpose",
            r"V_i^l": "V sub i superscript l",
            r"u^\star=P\,\epsilon-x_0,\qquad P=A_eA_e^\top": "u star equals P epsilon minus x sub 0, P equals A sub e A sub e transpose",
        }
        for tex, words in cases.items():
            with self.subTest(tex):
                self.assertEqual(say(tex), words)

    def test_every_equation_reads_without_tex_left_in_it(self):
        for name, tex in ALL:
            with self.subTest(name):
                words = say(tex)
                self.assertTrue(words)
                self.assertNotRegex(words, r"\\|[{}^_]|rangle|langle")

    def test_the_reading_is_in_every_output(self):
        svg = render_svg(r"e^{i\pi}+1=0")
        self.assertEqual(ElementTree.fromstring(svg).find("{http://www.w3.org/2000/svg}desc").text, say(r"e^{i\pi}+1=0"))
        self.assertIn("// Read: e to the i pi plus 1 equals 0", render_glsl(r"e^{i\pi}+1=0"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--read", self.LOSS]), 0)
        self.assertEqual(out.getvalue().strip(), read(self.LOSS))

    def test_the_web_buttons_are_glyphs_and_the_reading_is_a_popover(self):
        page = render_html(self.LOSS, legend=True)
        for button in re.findall(r"<button [^>]*>.*?</button>", page):
            with self.subTest(button[:60]):
                # No words on the face of a button: a glyph, with the words in its label and title.
                self.assertEqual(re.sub(r"<[^>]+>", "", button).strip(), "")
                self.assertRegex(button, r'aria-label="[^"]+" title="[^"]+"')
        pid = re.search(r'class="eqlens-read"[^>]*popovertarget="(eqread[0-9a-f]+)"', page).group(1)
        self.assertIn(f'<div class="eqlens-said" id="{pid}" popover', page)
        self.assertIn(html_escape(read(self.LOSS)), page)
        self.assertIn(f'data-say="{html_escape(say(self.LOSS), quote=True)}"', page)
        # It sits outside the drawing, so opening it changes nothing in the figure's size.
        closed = page.split('<div class="eqlens-closed">')[1].split("</div>")[0]
        self.assertNotIn("eqlens-said", closed)


class GlslTests(unittest.TestCase):
    TEX = SymbolTests.TEX

    def test_a_shader_is_webgl2_with_a_shadertoy_main_inside(self):
        source = render_glsl(r"e^{i\pi}+1=0")
        self.assertTrue(source.startswith("#version 300 es\n"))
        inner = source.split("// ---- Shadertoy: paste from here ----")[1].split("// ---- Shadertoy: paste to here ----")[0]
        self.assertIn("void mainImage(out vec4 fragColor, in vec2 fragCoord)", inner)
        self.assertNotIn("#version", inner)
        self.assertNotIn("uniform", inner)
        self.assertIn("mainImage(eqlensColor, gl_FragCoord.xy)", source)

    def test_array_sizes_match_their_entries(self):
        source = render_glsl(self.TEX, legend=True, define=["P=what one token can carry"], notes=["fine print"])
        for kind, name, size, body in re.findall(r"const (\w+) (\w+)\[(\d+)\] = \w+\[\]\(\n(.*?)\n\);", source, re.S):
            with self.subTest(name):
                self.assertEqual(int(size), body.count(f"{kind}("))
        self.assertIn("const int RULES = 0;", render_glsl("x"))
        self.assertIn("RULE[1] = vec4[](\n  vec4(0)", render_glsl("x"))

    def test_the_shader_draws_the_same_scene_as_the_svg(self):
        svg = render_svg(self.TEX, legend=True, credit=False)
        source = render_glsl(self.TEX, legend=True)
        marks = int(re.search(r"const int MARKS = (\d+);", source).group(1))
        self.assertEqual(marks, svg.count("<use "))
        width, height = (float(v) for v in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).group(1, 2))
        scene = re.search(r"SCENE = vec2\(([\d.]+), ([\d.]+)\)", source)
        self.assertAlmostEqual(float(scene.group(1)), width, places=1)
        self.assertAlmostEqual(float(scene.group(2)), height, places=1)

    def test_a_symbol_and_its_row_share_a_hover_bit(self):
        source = render_glsl(self.TEX, define=["P=what one token can carry"])
        # P: two glyphs in the formula and one row carry bit 0, and dim with the rest.
        self.assertEqual(source.count("uvec2(1u, 1u)"), 3)

    def test_colors_and_background(self):
        source = render_glsl("x", color="#ff0000")
        self.assertIn("vec3(1., 0., 0.)", source)
        self.assertIn("UNDER = vec4(0.)", source)
        self.assertIn("UNDER = vec4(0.071, 0.078, 0.102, 1.)", render_glsl("x", notes=["a card"]))

    def test_the_command_line_picks_glsl_from_the_name(self):
        for suffix in (".glsl", ".frag"):
            path = self.id().replace(".", "_") + suffix
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["--local", "-o", path, r"E=mc^2"]), 0)
                with open(path, encoding="utf-8") as handle:
                    self.assertTrue(handle.read().startswith("#version 300 es"))
            finally:
                if os.path.exists(path):
                    os.remove(path)


class TextTests(unittest.TestCase):
    def test_draws_the_formula_in_dots_with_the_ledger_in_words(self):
        from eqlens.text import ansi, cells

        found = cells(r"e^{i\pi}+1=0", columns=80, legend=True, notes=["A note."])
        self.assertTrue(found["fits"])
        ink = "".join(text for line in found["picture"] for text, _tint in line)
        self.assertTrue(any(0x2800 < ord(ch) <= 0x28FF for ch in ink))
        self.assertTrue(all(len("".join(text for text, _tint in line)) <= 80 for line in found["picture"]))
        row = next(row for row in found["ledger"] if row["glyph"] == "π")
        self.assertEqual(row["words"], "pi")
        # Pi keeps its ledger color in the drawing, and plain ink carries none.
        tints = {tint for line in found["picture"] for _text, tint in line}
        self.assertIn(row["color"], tints)
        self.assertIn(None, tints)
        shown = ansi(found)
        self.assertIn("\033[38;2;", shown)
        self.assertNotIn("\033", ansi(found, color=False))
        self.assertIn("A note.", shown)

    def test_a_long_formula_is_drawn_smaller_and_says_so(self):
        from eqlens.text import cells

        found = cells(r"W_c=\left(Z_c^TZ_c+\lambda n_cI\right)^{-1}Z_c^TY_c+a+b+c+d+e+f+g+h", columns=40)
        self.assertFalse(found["fits"])
        self.assertTrue(all(len("".join(text for text, _tint in line)) <= 40 for line in found["picture"]))
        with self.assertRaises(FormulaError):
            cells("x=1", columns=5)

    def test_the_command_prints_dots_or_json(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--display", "text", "--columns", "50", "--legend", r"e^{i\pi}+1=0"]), 0)
        self.assertIn("pi", out.getvalue())
        self.assertNotIn("\033", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--display", "cells", "--columns", "50", "x=1"]), 0)
        self.assertEqual(json.loads(out.getvalue())["tex"], "x=1")


class BurnTests(unittest.TestCase):
    def test_a_comment_fits_the_language_and_the_width(self):
        from eqlens.text import comment

        block = comment(r"E=mc^2", "gamma.py", width=60, legend=True, notes=["Rest energy."])
        lines = block.rstrip("\n").split("\n")
        self.assertTrue(all(line.startswith("#") and len(line) <= 60 for line in lines))
        self.assertTrue(lines[0].startswith("# ── eqlens ─"))
        self.assertIn("#    E=mc^2", lines)
        self.assertIn("Rest energy.", block)
        self.assertNotIn("\033", block)
        self.assertFalse(any(line != line.rstrip() for line in lines))
        self.assertTrue(comment("x=1", "//").startswith("// ── eqlens"))
        css = comment("x=1", "a.css").split("\n")
        self.assertEqual((css[0], css[-2]), ("/*", " */"))
        self.assertTrue(comment("x=1", "index.html").startswith("<!--\n"))
        with self.assertRaises(FormulaError):
            comment("x=1", "notes.xyz")
        with self.assertRaises(FormulaError):
            comment("x--", "index.html")

    def test_burn_goes_under_the_first_line_and_is_not_added_twice(self):
        import tempfile

        from eqlens.text import burn

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "g.py")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("#!/usr/bin/env python3\nimport math\n")
            self.assertEqual(burn(path, r"E=mc^2"), "added")
            with open(path, encoding="utf-8") as handle:
                once = handle.read()
            lines = once.split("\n")
            self.assertEqual(lines[0], "#!/usr/bin/env python3")
            self.assertTrue(lines[1].startswith("# ── eqlens"))
            self.assertTrue(once.endswith("\n\nimport math\n"))
            self.assertEqual(burn(path, r"E=mc^2"), "replaced")
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), once)
            # The same formula with a note still replaces its block; another formula gets a block of its own.
            self.assertEqual(burn(path, r"E=mc^2", notes=["Rest energy."]), "replaced")
            self.assertEqual(burn(path, r"F=ma"), "added")
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertEqual(text.count("── eqlens"), 2)
            self.assertIn("Rest energy.", text)
            self.assertTrue(text.endswith("import math\n"))

            sheet = os.path.join(folder, "a.css")
            with open(sheet, "w", encoding="utf-8") as handle:
                handle.write("body { color: red; }\n")
            self.assertEqual(burn(sheet, "x=1"), "added")
            self.assertEqual(burn(sheet, "x=1"), "replaced")
            with open(sheet, encoding="utf-8") as handle:
                text = handle.read()
            self.assertEqual((text.count("/*"), text.count("*/")), (1, 1))

    def test_the_command_and_the_mcp_tool_burn(self):
        import tempfile

        from eqlens.mcp import handle as answer

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "m.rs")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("fn main() {}\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["--burn", path, "F=ma"]), 0)
            self.assertTrue(out.getvalue().startswith("added: "))
            with open(path, encoding="utf-8") as handle:
                self.assertTrue(handle.read().startswith("// ── eqlens"))
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(main(["--burn", os.path.join(folder, "none.py"), "F=ma"]), 1)

            def call(arguments):
                message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call"}
                message["params"] = {"name": "eqlens_comment", "arguments": arguments}
                return answer(message)["result"]

            shown = call({"tex": "F=ma", "style": "py"})
            self.assertTrue(shown["content"][0]["text"].startswith("# ── eqlens"))
            done = call({"tex": "F=ma", "file": path, "write": True})
            self.assertEqual(done["content"][0]["text"], "replaced: " + path)
            self.assertTrue(call({"tex": "F=ma"}).get("isError"))


class DiagramTests(unittest.TestCase):
    FOLD = r"L_0' = \mathrm{Conv}_\theta(L_0, L_1, C_0),\quad L_1' = \mathrm{Conv}_\theta(C_1, \ldots, C_5),\quad S' = (C_6, C_7)"

    def test_a_formula_that_works_out_is_drawn_as_its_steps(self):
        from eqlens.diagram import diagram

        found = diagram(r"E = \frac{1}{2} m v^2 + m g h", define=["m=the mass"])
        self.assertEqual((found["kind"], found["fits"], found["steps"]), ("steps", True, 4))
        source = found["mermaid"]
        self.assertIn("flowchart LR", source)
        for label in ('(["times 1/2"])', '(["square"])', '(["add"])', '[["E"]]'):
            self.assertIn(label, source)
        # m is used twice and is one box, in the color the drawing gives it.
        self.assertEqual(source.count('["m"]'), 1)
        self.assertRegex(source, r'\["m"\]:::c0')
        self.assertIn("stroke:#ffa657", source)
        gauss = diagram(r"f(x) = \frac{1}{\sigma\sqrt{2\pi}} e^{-\frac{(x-\mu)^2}{2\sigma^2}}", legend=True)
        self.assertTrue(gauss["fits"])
        self.assertIn('-- "take away" -->', gauss["mermaid"])
        self.assertIn('-- "bottom" -->', gauss["mermaid"])

    def test_a_formula_that_names_what_is_done_is_drawn_as_its_calls(self):
        from eqlens.diagram import diagram

        found = diagram(self.FOLD, define=[r"\mathrm{Conv}_\theta=folds five slots into one"])
        self.assertEqual((found["kind"], found["fits"], found["steps"]), ("calls", True, 2))
        source = found["mermaid"]
        self.assertEqual(source.count('{{"Conv_θ"}}:::c0'), 2)
        for label in ('["L₀′"]', '["C₁ … C₅"]', '-- "kept" -->'):
            self.assertIn(label, source)
        # A result that is used again is one box: z runs out of f and into g.
        chain = diagram(r"z = f(x, y),\quad w = g(z)", style="plain")
        self.assertTrue(chain["fits"])
        self.assertEqual(chain["mermaid"].count('["z"]'), 1)
        self.assertNotIn("%%{init", chain["mermaid"])
        self.assertNotIn("fill:", chain["mermaid"])

    def test_it_says_when_a_diagram_would_add_nothing(self):
        from eqlens.diagram import diagram
        from eqlens.engine import FormulaError

        one = diagram("F = m a")
        self.assertFalse(one["fits"])
        self.assertIn("one step", one["why"])
        self.assertIn("flowchart", one["mermaid"])
        none = diagram(r"\int_0^1 x\,dx = \frac{1}{2}")
        self.assertEqual((none["fits"], none["mermaid"]), (False, ""))
        self.assertIn("integral", none["why"])
        with self.assertRaises(FormulaError):
            diagram("x=1", style="neon")

    def test_the_command_and_the_tools(self):
        import tempfile

        from eqlens.mcp import handle as answer

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--diagram", "light", "--direction", "TB", r"E = \frac{1}{2} m v^2 + m g h"]), 0)
        self.assertIn("flowchart TB", out.getvalue())
        self.assertIn('"theme": "neutral"', out.getvalue())
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "flow.md")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--diagram", "dark", "-o", path, self.FOLD]), 0)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertTrue(text.startswith("```mermaid\n") and text.endswith("```\n"))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main(["--diagram", "dark", r"\sum_i x_i = 1"]), 1)
        self.assertIn("no diagram", err.getvalue())

        def call(name, arguments):
            message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
            return answer(message)["result"]

        found = json.loads(call("eqlens_diagram", {"tex": self.FOLD})["content"][0]["text"])
        self.assertTrue(found["fits"])
        self.assertIn("flowchart LR", found["mermaid"])
        drawn = call("eqlens_render", {"tex": self.FOLD, "format": "svg"})
        self.assertIn("eqlens_diagram", drawn["content"][-1]["text"])
        plain_ = call("eqlens_render", {"tex": "F=ma", "format": "svg"})
        self.assertEqual(len(plain_["content"]), 1)


class PopTests(unittest.TestCase):
    GAUSS = r"f(x) = \frac{1}{\sigma\sqrt{2\pi}} e^{-\frac{(x-\mu)^2}{2\sigma^2}}"

    def cards(self, page):
        found = re.search(r'<script type="application/json" class="eqlens-pops">(.*?)</script>', page, re.S)
        return json.loads(found.group(1)) if found else None

    def test_a_symbol_gets_its_words_and_a_curve_of_the_result(self):
        page = render_html(self.GAUSS, legend=True, define=[r"\sigma=the spread"])
        cards = self.cards(page)
        sigma = next(card for card in cards if card["g"] == "σ")
        self.assertEqual((sigma["t"], sigma["n"], sigma["out"]), ("sigma", "the spread", "f"))
        self.assertEqual(len(sigma["ys"]), 49)
        self.assertLess(sigma["lo"], sigma["at"])
        self.assertLess(sigma["at"], sigma["hi"])
        # A wider bell is a lower one where it stands.
        self.assertGreater(sigma["ys"][10], sigma["ys"][-1])
        self.assertIn("eqlens-hint", page)
        self.assertIn("__eqlensPop", page)

    def test_a_card_sits_at_its_symbols_class_in_the_drawing(self):
        page = render_html(self.GAUSS, legend=True)
        cards = self.cards(page)
        for index, card in enumerate(cards):
            self.assertIn(f" s{index}", page, card)

    def test_a_formula_that_cannot_be_worked_out_still_gets_the_words(self):
        page = render_html(dict(ALL)["schrodinger"], legend=True, define=[r"\Psi=the wave function"])
        cards = self.cards(page)
        self.assertTrue(cards)
        self.assertFalse(any("ys" in card for card in cards))
        self.assertIn("the wave function", [card["n"] for card in cards])

    def test_a_part_over_the_sum_of_all_parts_is_drawn_as_shares(self):
        softmax = r"\sigma(z)_i=\frac{e^{z_i}}{\sum_{j=1}^{K}e^{z_j}}"
        page = render_html(softmax, brief=True, define=["z_i=the raw score for class i"], sets=["z_i=1:-2:4", "K=3"])
        card = next(card for card in self.cards(page) if "bs" in card)
        self.assertEqual((card["g"], card["lo"], card["hi"], card["out"]), ("z_i", -2.0, 4.0, "σ(z)_i"))
        self.assertEqual(len(card["bs"]), 49)
        self.assertEqual(card["bx"], [0.0, 2.0])
        for shares in card["bs"]:
            self.assertEqual(len(shares), 3)
            self.assertAlmostEqual(sum(shares), 1.0, places=3)
        # A higher score is a larger share, and it is taken from the others.
        self.assertLess(card["bs"][0][0], card["bs"][-1][0])
        self.assertGreater(card["bs"][0][2], card["bs"][-1][2])
        self.assertEqual(card["ys"], [shares[0] for shares in card["bs"]])
        # Read from the shape, not the name: a Boltzmann weight is the same kind of formula.
        boltzmann = r"p_i=\frac{e^{-E_i/T}}{\sum_{j} e^{-E_j/T}}"
        cards = self.cards(render_html(boltzmann, define=["E_i=the energy of state i"]))
        energy = next(card for card in cards if "bs" in card)
        self.assertEqual(len(energy["bs"][0]), 4)
        self.assertGreater(energy["bs"][0][0], energy["bs"][-1][0])
        # A ratio that is not a part of its own sum keeps the words only.
        other = self.cards(render_html(r"y_i=\frac{a_i}{\sum_{j} b_j}", define=["a_i=one part"]))
        self.assertFalse(any("bs" in card for card in other))

    def test_exp_and_ln_are_named_and_get_their_own_curve(self):
        bell = r"f(x)=\frac{1}{\sigma\sqrt{2\pi}}\exp\left(-\frac{(x-\mu)^{2}}{2\sigma^{2}}\right)"
        cards = self.cards(render_html(bell, legend=True, sets=["x=0:-4:4", r"\mu=0:-2:2"]))
        exp = next(card for card in cards if card["g"] == "exp")
        self.assertEqual((exp["t"], exp["out"], exp["ax"]), ("exponential", "exp", "what is inside"))
        self.assertIn("multiplies the result by e", exp["n"])
        # What is inside a bell's exp runs from -8 up to 0 as x crosses its range, so exp stays between 0 and 1.
        self.assertEqual((exp["lo"], exp["hi"]), (-8.0, 0.0))
        self.assertEqual(exp["ys"][-1], 1.0)
        self.assertTrue(all(0 < y <= 1 for y in exp["ys"]))
        # e to a power is the same function: its card goes to e when e has a row.
        power = r"f(x)=e^{-x^{2}}"
        e = next(card for card in self.cards(render_html(power, define=["e=Euler's number"])) if card["g"] == "e")
        self.assertEqual((e["out"], e["hi"]), ("exp", 0.0))
        ln = next(card for card in self.cards(render_html(r"S=k\ln W", legend=True)) if card["g"] == "ln")
        self.assertEqual((ln["t"], ln["out"]), ("natural log", "ln"))
        self.assertLess(ln["ys"][0], ln["ys"][-1])
        # With no legend there is no row for exp, and so no card.
        self.assertFalse(any(card.get("ax") for card in self.cards(render_html(bell, define=["f=the height"]))))

    def test_a_card_can_link_to_where_the_symbol_is_explained(self):
        from eqlens.engine import FormulaError

        page = render_html("E=mc^2", define=["m=the mass"], link=["m=https://example.org/mass?t=3 What mass is"])
        card = next(card for card in self.cards(page) if card["g"] == "m")
        self.assertEqual(card["m"], ["https://example.org/mass?t=3", "What mass is"])
        bare = render_html("E=mc^2", define=["m=the mass"], link=["m=https://www.example.org/x"])
        self.assertEqual(next(card for card in self.cards(bare) if card["g"] == "m")["m"][1], "example.org")
        for bad in ("m=javascript:alert(1)", "m=", "q=https://example.org"):
            with self.assertRaises(FormulaError):
                render_html("E=mc^2", define=["m=the mass"], link=[bad])
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "e.html")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--define", "m=the mass", "--link", "m=https://example.org", "-o", path, "E=mc^2"]), 0)
            with open(path, encoding="utf-8") as handle:
                self.assertIn('"m":["https://example.org","example.org"]', handle.read())

    def test_sets_and_constants_shape_the_curve(self):
        page = render_html(
            r"E^2 = (pc)^2 + (mc^2)^2", constant=["c"], define=["m=rest mass"], sets=["m=1e-30:0:3e-30:kg", "p=1e-22:0:5e-22"]
        )
        cards = {card["g"]: card for card in self.cards(page)}
        self.assertEqual((cards["m"]["lo"], cards["m"]["hi"], cards["m"]["u"]), (0.0, 3e-30, "kg"))
        self.assertEqual(cards["c"]["v"], 299792458.0)
        self.assertNotIn("ys", cards["c"])

    def test_nothing_to_say_means_no_cards_and_no_script(self):
        page = render_html(r"a^2+b^2=c^2")
        self.assertIsNone(self.cards(page))
        self.assertNotIn("__eqlensPop", page)
        off = render_html(self.GAUSS, legend=True, pop=False)
        self.assertIsNone(self.cards(off))
        self.assertNotIn("__eqlensPop", off)

    def test_words_only_leaves_the_plot_out(self):
        cards = self.cards(render_html(self.GAUSS, legend=True, define=[r"\sigma=the spread"], pop="words"))
        self.assertFalse(any("ys" in card or "now" in card for card in cards))
        self.assertIn("the spread", [card["n"] for card in cards])

    def test_card_text_cannot_close_its_script(self):
        page = render_html(r"a+b", define=["a=</script><b>x"])
        self.assertEqual(page.count("</script>"), 3)
        self.assertIn("\\u003c/script>", page)

    def test_the_command_line_takes_set_and_no_pop(self):
        path = os.path.join(self.id().replace(".", "_") + ".html")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--local", "--define", "a=one side", "--set", "a=3:1:9", "-o", path, r"c=\sqrt{a^2+b^2}"]), 0)
            with open(path, encoding="utf-8") as handle:
                card = next(card for card in self.cards(handle.read()) if card["g"] == "a")
            self.assertEqual((card["lo"], card["at"], card["hi"]), (1.0, 3.0, 9.0))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--local", "--define", "a=one side", "--no-pop", "-o", path, r"c=\sqrt{a^2+b^2}"]), 0)
            with open(path, encoding="utf-8") as handle:
                self.assertIsNone(self.cards(handle.read()))
        finally:
            if os.path.exists(path):
                os.remove(path)


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason


class _Claude:
    """Stands in for anthropic.Anthropic: records the request and returns a canned answer."""

    def __init__(self, answer, stop_reason="end_turn"):
        self.messages = self
        self.answer = answer
        self.stop_reason = stop_reason
        self.request = None

    def create(self, **request):
        self.request = request
        text = self.answer if isinstance(self.answer, str) else json.dumps(self.answer)
        return _Response(text, self.stop_reason)


@unittest.skipUnless(importlib.util.find_spec("anthropic"), "the anthropic package is not installed")
class IntrospectTests(unittest.TestCase):
    TEX = dict(ALL)["einstein field"]
    ANSWER = {
        "name": "Einstein field equations",
        "about": "Matter and energy tell spacetime how to curve.",
        "symbols": [
            {"key": r"G_{\mu\nu}", "meaning": "how spacetime curves."},
            {"key": r"T_{\mu\nu}", "meaning": "the matter and energy that is there"},
            {"key": r"\Lambda", "meaning": "the cosmological constant"},
            {"key": "Q_7", "meaning": "a part that is not in the formula"},
            {"key": r"\frac{", "meaning": "broken TeX"},
            {"key": "c", "meaning": ""},
        ],
    }

    def test_claude_is_asked_about_this_formula(self):
        claude = _Claude(self.ANSWER)
        introspect(self.TEX, context="From a relativity lecture.", client=claude)
        self.assertEqual(claude.request["model"], "claude-opus-5-5")
        self.assertEqual(claude.request["output_config"]["format"]["type"], "json_schema")
        prompt = claude.request["messages"][0]["content"]
        self.assertIn(self.TEX, prompt)
        self.assertIn(r"G_{\mu\nu}", prompt)
        self.assertIn("From a relativity lecture.", prompt)

    def test_only_parts_that_are_in_the_formula_are_kept(self):
        found = introspect(self.TEX, client=_Claude(self.ANSWER))
        self.assertEqual(found["name"], "Einstein field equations")
        self.assertEqual(
            found["define"],
            [
                r"G_{\mu\nu}=how spacetime curves",
                r"T_{\mu\nu}=the matter and energy that is there",
                r"\Lambda=the cosmological constant",
            ],
        )
        svg = render_svg(self.TEX, brief=True, define=found["define"])
        self.assertGreaterEqual(svg.count("s0"), 2)

    def test_claude_can_open_a_part_into_its_formula(self):
        tex = r"\gamma m c^2"
        answer = {
            "name": "",
            "about": "Energy of a moving body.",
            "symbols": [
                {"key": r"\gamma", "meaning": "how much motion stretches time", "inside": r"\frac{1}{\sqrt{1-v^2/c^2}}"},
                {"key": "m", "meaning": "the mass", "inside": r"\frac{"},
                {"key": "c", "meaning": "the speed of light", "inside": ""},
            ],
        }
        found = introspect(tex, client=_Claude(answer))
        self.assertEqual(found["tier"], [r"\gamma=\frac{1}{\sqrt{1-v^2/c^2}}"])
        self.assertEqual(len(found["define"]), 3)
        kept = introspect(tex, tier=[r"\gamma=1+x"], client=_Claude(answer))
        self.assertEqual(kept["tier"], [r"\gamma=1+x"])
        self.assertTrue(render_svg(found["tex"], brief=True, define=found["define"], tier=found["tier"]))

    def test_what_the_caller_defined_wins(self):
        found = introspect(self.TEX, define=[r"G_{\mu\nu}=the left side"], client=_Claude(self.ANSWER))
        self.assertEqual(found["define"][0], r"G_{\mu\nu}=the left side")
        self.assertEqual(sum(item.startswith("G_") for item in found["define"]), 1)

    def test_a_refusal_or_a_bad_answer_is_an_error(self):
        with self.assertRaises(IntrospectError):
            introspect(self.TEX, client=_Claude(self.ANSWER, stop_reason="refusal"))
        with self.assertRaises(IntrospectError):
            introspect(self.TEX, client=_Claude("not json"))
        with self.assertRaises(IntrospectError):
            introspect(self.TEX, client=_Claude("[1, 2]"))


class InspectTests(unittest.TestCase):
    def test_inspect_lists_the_parts(self):
        found = inspect(r"$u^\star=P\,\epsilon-x_0$", define=["P=what one token can carry"])
        self.assertEqual(found["tex"], r"u^\star=P\,\epsilon-x_0")
        by_key = {row["key"]: row for row in found["symbols"]}
        self.assertEqual(by_key[r"u^{\star}"]["says"], "u star")
        self.assertEqual(by_key["P"], {"key": "P", "says": "", "means": "what one token can carry", "defined": True, "appears": 1})
        self.assertEqual(by_key[r"\epsilon"]["appears"], 1)

    def test_inspect_flag_prints_json_and_draws_nothing(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--inspect", r"A_e^\top A_e=I"]), 0)
        found = json.loads(out.getvalue())
        self.assertEqual([row["says"] for row in found["symbols"]], ["A sub e", "A_e transpose"])


class CliTests(unittest.TestCase):
    def test_output_file(self):
        path = os.path.join(self.id().replace(".", "_") + ".png")
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["--local", "-o", path, r"E=mc^2"])
            self.assertEqual(code, 0)
            self.assertEqual(out.getvalue().strip(), os.path.abspath(path))
            with open(path, "rb") as handle:
                self.assertTrue(handle.read(8).startswith(b"\x89PNG"))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_output_is_svg_unless_the_name_says_png(self):
        path = os.path.join(self.id().replace(".", "_") + ".svg")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--local", "--legend", "-o", path, r"E=mc^2"]), 0)
            with open(path, "rb") as handle:
                self.assertTrue(handle.read(4).startswith(b"<svg"))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--local", "--format", "png", "-o", path, r"E=mc^2"]), 0)
            with open(path, "rb") as handle:
                self.assertTrue(handle.read(8).startswith(b"\x89PNG"))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_iterm_protocol_matches_imgcat(self):
        png = render_png(r"E=mc^2")
        buf = io.BytesIO()
        display_png(png, "iterm", buf)
        data = buf.getvalue()
        self.assertTrue(data.startswith(b"\033]1337;File=inline=1;"))
        self.assertIn(b"\a", data)


if __name__ == "__main__":
    unittest.main()
