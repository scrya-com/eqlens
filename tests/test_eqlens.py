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
from eqlens.legend import MAX_TIERS, greek_in, hints_in, notation_in, occurrences, plain, plan, symbols
from eqlens.render import FormulaError, render_html, render_png, render_svg
from eqlens.server import Handler


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
        self.assertIn("h bar. Planck's constant divided by 2π.", tips)
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
        self.assertEqual(page.count("<svg "), 1)

    def test_tiers_add_an_expand_button_and_a_second_drawing(self):
        page = render_html(self.TEX, define=["P=keeps the coarse part"], tier=TierTests.TIERS)
        self.assertEqual(page.count('class="eqlens-expand"'), 1)
        self.assertEqual(page.count("<svg "), 2)
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
