import contextlib
import importlib.util
import io
import json
import math
import os
import re
import tempfile
import unittest

from equations import ALL

from eqlens.bench import Unreadable, build, curve, data, load, make, points, work_out
from eqlens.bench.expr import from_tex, from_text, isolate, slug, symbols_in, to_excel, to_js, to_python, to_tex, to_text, value
from eqlens.bench.spec import tree
from eqlens.cli import main
from eqlens.engine import FormulaError
from eqlens.introspect import IntrospectError, workable
from eqlens.mcp import TOOLS, handle, serve
from eqlens.render import render_svg

TEX = dict(ALL)
GAUSS = TEX["gaussian"]
GAUSS_SETS = ["x=0:-4:4", r"\mu=0:-2:2", r"\sigma=1:0.3:3"]

# The formulas in tests/equations.py that are real and closed-form, and so are read as written.
READ = [
    "newton", "gravitation", "kinetic energy", "lorentz factor", "energy-momentum", "boltzmann entropy", "ideal gas",
    "planck law", "gaussian", "de broglie", "oscillator levels", "diffusion forward", "adam moment", "layer norm",
    "sigmoid",
]
# Ones that must be refused, and a word from the reason.
REFUSED = {
    "schrodinger": "derivative", "wave": "derivative", "fourier transform": "integral", "density matrix": "sum",
    "uncertainty": "inequality", "expectation": "bra-ket", "unitary": "matrix", "ridge regression": "matrix",
    "born rule": "function", "von neumann entropy": "function", "euler-lagrange": "derivative", "bellman": "maximum",
}


def excel(formula: str, cells: dict[str, float]) -> float:
    """Work a cell formula out by Excel's own rules: a minus sign binds tighter than ^, and ^ runs left to right."""
    tokens = re.findall(r"\d+\.?\d*(?:[eE][-+]?\d+)?|[A-Za-z_][A-Za-z_0-9]*|[-+*/^(),]", formula)
    at = 0

    def peek():
        return tokens[at] if at < len(tokens) else None

    def take():
        nonlocal at
        at += 1
        return tokens[at - 1]

    def sum_():
        left = product()
        while peek() in ("+", "-"):
            left = left + product() if take() == "+" else left - product()
        return left

    def product():
        left = power()
        while peek() in ("*", "/"):
            left = left * power() if take() == "*" else left / power()
        return left

    def power():
        left = signed()
        while peek() == "^":
            take()
            left = left ** signed()
        return left

    def signed():
        if peek() == "-":
            take()
            return -signed()
        return atom()

    def atom():
        token = take()
        if token == "(":
            inside = sum_()
            take()
            return inside
        if re.match(r"\d", token):
            return float(token)
        if peek() == "(":
            take()
            args = []
            while peek() != ")":
                args.append(sum_())
                if peek() == ",":
                    take()
            take()
            name = token.upper()
            if name == "PI":
                return math.pi
            if name == "LOG":
                return math.log(args[0], args[1])
            return {"SQRT": math.sqrt, "EXP": math.exp, "LN": math.log, "LOG10": math.log10, "ABS": abs,
                    "SIN": math.sin, "COS": math.cos, "TAN": math.tan, "ASIN": math.asin, "ACOS": math.acos,
                    "ATAN": math.atan, "SINH": math.sinh, "COSH": math.cosh, "TANH": math.tanh}[name](args[0])
        return cells[token]

    return sum_()


class ReadingTests(unittest.TestCase):
    def test_closed_form_formulas_are_read_as_written(self):
        for name in READ:
            with self.subTest(name):
                out, _args, node = from_tex(TEX[name])
                self.assertIsNotNone(out)
                self.assertTrue(symbols_in(node))

    def test_what_cannot_be_worked_out_is_refused_with_the_reason(self):
        for name, word in REFUSED.items():
            with self.subTest(name), self.assertRaises(Unreadable) as caught:
                from_tex(TEX[name])
            self.assertIn(word, str(caught.exception))

    def test_every_formula_is_read_or_refused_and_never_crashes(self):
        for name, tex in ALL:
            with self.subTest(name):
                try:
                    from_tex(tex)
                except Unreadable:
                    pass

    def test_gaussian_has_the_right_value(self):
        out, args, node = from_tex(GAUSS)
        self.assertEqual((out, args), ("f", ("x",)))
        self.assertAlmostEqual(value(node, {"x": 0.0, r"\mu": 0.0, r"\sigma": 1.0}), 1 / math.sqrt(2 * math.pi))

    def test_what_could_be_read_two_ways_is_refused(self):
        with self.assertRaises(Unreadable) as caught:
            from_tex(r"y=\log x")
        self.assertIn("base 10 or the natural log", str(caught.exception))
        self.assertAlmostEqual(value(from_tex(r"y=\log_{10} x")[2], {"x": 1000.0}), 3.0)
        with self.assertRaises(Unreadable) as caught:
            build(r"y=Ae^{ikx}")
        self.assertIn("imaginary unit", str(caught.exception))
        self.assertEqual(build(r"y=a_i+i", sets=["i=2:1:5"])["sweep"], "a_i")

    def test_a_slash_divides_by_everything_written_after_it(self):
        _out, _args, node = from_tex(r"y=e^{h\nu/k_BT}")
        self.assertAlmostEqual(value(node, {"h": 2.0, r"\nu": 3.0, "k_B": 4.0, "T": 5.0}), math.exp(6 / 20))

    def test_minus_a_square_is_negative(self):
        self.assertEqual(value(from_tex(r"y=-x^2")[2], {"x": 3.0}), -9.0)

    def test_a_function_without_brackets_takes_the_factors_after_it(self):
        node = from_tex(r"y=\sin^2 2\pi x+\ln\Omega")[2]
        self.assertAlmostEqual(value(node, {"x": 0.3, r"\Omega": 5.0}), math.sin(0.6 * math.pi) ** 2 + math.log(5))

    def test_star_and_accents_name_a_symbol_and_are_not_powers(self):
        out, _args, node = from_tex(r"u^\star=P\,\epsilon-x_0")
        self.assertEqual(out, r"u^\star")
        self.assertEqual(symbols_in(from_tex(r"y=\bar{\alpha}_t\hat{x}")[2]), [r"\bar{\alpha}_t", r"\hat{x}"])
        self.assertEqual(slug(r"\bar{\alpha}_t"), "alpha_bar_t")

    def test_no_real_value_is_nan_and_not_an_error(self):
        node = from_tex(TEX["lorentz factor"])[2]
        self.assertTrue(math.isnan(value(node, {"v": 2.0, "c": 1.0})))
        self.assertTrue(math.isnan(value(node, {"v": 1.0, "c": 1.0})))

    def test_a_formula_with_no_symbol_alone_is_solved_for_one(self):
        out, _args, node = from_tex("PV=nRT")
        self.assertEqual(out, "P")
        self.assertEqual(value(node, {"n": 2.0, "R": 3.0, "T": 4.0, "V": 6.0}), 4.0)
        out, _args, node = from_tex("PV=nRT", solve="T")
        self.assertEqual(value(node, {"n": 2.0, "R": 3.0, "P": 4.0, "V": 6.0}), 4.0)

    def test_solving_undoes_powers_roots_and_logs(self):
        out, _args, node = from_tex(TEX["energy-momentum"])
        self.assertEqual(out, "E")
        self.assertAlmostEqual(value(node, {"p": 3.0, "c": 1.0, "m": 4.0}), 5.0)
        node = from_tex(TEX["boltzmann entropy"], solve=r"\Omega")[2]
        self.assertAlmostEqual(value(node, {"S": 6.0, "k_B": 2.0}), math.exp(3))
        with self.assertRaises(Unreadable):
            from_tex(TEX["lorentz factor"], solve="q")
        with self.assertRaises(Unreadable):
            isolate(("sym", "y"), ("mul", ("sym", "x"), ("sym", "x")), "x")

    def test_plain_text_reads_back_what_was_written(self):
        for name in READ:
            with self.subTest(name):
                node = from_tex(TEX[name])[2]
                keys = symbols_in(node)
                again = from_text(to_text(node), {slug(key): key for key in keys})[1]
                env = {key: 0.4 + 0.3 * i for i, key in enumerate(keys)}
                a, b = value(node, env), value(again, env)
                self.assertTrue((math.isnan(a) and math.isnan(b)) or math.isclose(a, b, rel_tol=1e-12))

    def test_plain_text_takes_a_caret_for_a_power_and_lambda_for_a_name(self):
        out, node = from_text("f = lambda*2 + x^2", {"lambda": r"\lambda", "x": "x"})
        self.assertEqual(out, "f")
        self.assertEqual(value(node, {r"\lambda": 5.0, "x": 3.0}), 19.0)

    def test_plain_text_runs_no_code(self):
        for text in ("__import__('os').system('true')", "x.real", "[x for x in y]", "open('f')", "x if x else 1", "'a'*3"):
            with self.subTest(text), self.assertRaises(Unreadable):
                from_text(text, {"x": "x", "y": "y"})


class WritingTests(unittest.TestCase):
    """Every dialect must give the number eqlens gives."""

    def env(self, node):
        return {key: 0.35 + 0.45 * i for i, key in enumerate(symbols_in(node))}

    def test_cell_formulas_agree_under_excels_rules(self):
        cases = [TEX[name] for name in READ] + [r"y=-x^2", r"y=-x^{-2}", r"y=2^{x^2}", r"y=(-x)^2-a^{b}", r"y=|x-a|^3+\sqrt[3]{x}"]
        for tex in cases:
            with self.subTest(tex):
                node = from_tex(tex)[2]
                env = self.env(node)
                cells = {slug(key) + "_": number for key, number in env.items()}
                want = value(node, env)
                got = excel(to_excel(node, lambda key: slug(key) + "_"), cells)
                self.assertTrue(math.isclose(got, want, rel_tol=1e-12), (got, want))

    def test_python_agrees(self):
        for name in READ:
            with self.subTest(name):
                node = from_tex(TEX[name])[2]
                env = self.env(node)
                names = {key: f"s{i}" for i, key in enumerate(env)}
                source = to_python(node, lambda key: names[key])
                got = eval(source, {"math": math, "__builtins__": {"abs": abs}}, {names[key]: number for key, number in env.items()})  # noqa: S307
                self.assertTrue(math.isclose(got, value(node, env), rel_tol=1e-12))

    def test_javascript_has_no_power_sign_to_misread(self):
        source = to_js(from_tex(r"y=-x^2+e^{-x}")[2])
        self.assertNotIn("**", source)
        self.assertIn("Math.pow(x,2)", source)
        self.assertIn("Math.exp(", source)

    def test_the_tex_written_back_draws_and_reads_the_same(self):
        for name in READ:
            with self.subTest(name):
                node = from_tex(TEX[name])[2]
                tex = "y=" + to_tex(node)
                self.assertIn("<svg", render_svg(tex))
                env = self.env(node)
                a, b = value(node, env), value(from_tex(tex)[2], env)
                self.assertTrue((math.isnan(a) and math.isnan(b)) or math.isclose(a, b, rel_tol=1e-12))


class SpecTests(unittest.TestCase):
    def test_gaussian_spec(self):
        spec = build(GAUSS, sets=GAUSS_SETS)
        self.assertEqual(spec["sweep"], "x")
        self.assertEqual(spec["output"]["key"], "f")
        self.assertEqual({entry["name"]: entry["role"] for entry in spec["symbols"]}, {"sigma": "parameter", "x": "variable", "mu": "parameter"})
        self.assertAlmostEqual(work_out(spec), 0.3989422804014327)
        self.assertFalse(spec["case"])
        self.assertTrue(spec["checked"].startswith("read from the formula"))

    def test_each_symbol_has_the_color_it_has_on_the_card(self):
        spec = build(GAUSS, sets=GAUSS_SETS)
        svg = render_svg(GAUSS, brief=True, define=spec["define"], known=False)
        for entry in spec["symbols"] + [spec["output"]]:
            with self.subTest(entry["name"]):
                self.assertIn(f'fill="{entry["color"]}"', svg)
                self.assertRegex(svg, rf'class="r s{entry["row"]} h')
        self.assertEqual(len({entry["color"] for entry in spec["symbols"] + [spec["output"]]}), 4)

    def test_a_spec_survives_json(self):
        for name, extra in (("gaussian", {"sets": GAUSS_SETS}), ("planck law", {"constant": ["h", "c", "k_B"]}), ("lorentz factor", {})):
            with self.subTest(name):
                spec = build(TEX[name], **extra)
                self.assertEqual(load(json.loads(json.dumps(spec))), spec)
        with self.assertRaises(FormulaError):
            load({"tex": "x"})

    def test_named_constants_hold_their_values_and_do_not_move(self):
        spec = build(TEX["planck law"], constant=["h", "c", "k_B"], sets=[r"\nu=3e14:1e13:2e15:Hz", "T=5000:1000:9000:K"], sweep=r"\nu")
        roles = {entry["name"]: entry for entry in spec["symbols"]}
        self.assertEqual(roles["c"]["role"], "constant")
        self.assertEqual(roles["c"]["value"], 299792458.0)
        self.assertNotIn("min", roles["h"])
        self.assertEqual(roles["nu"]["unit"], "Hz")
        self.assertAlmostEqual(work_out(spec), 2.3688592e-08, delta=1e-13)

    def test_the_range_is_one_where_the_formula_has_a_value(self):
        spec = build(TEX["lorentz factor"])
        v = next(entry for entry in spec["symbols"] if entry["name"] == "v")
        self.assertLess(v["max"], 1.0)
        self.assertFalse(math.isnan(work_out(spec)))
        self.assertTrue(all(not math.isnan(y) for y in curve(spec, "v")[1]))

    def test_an_expression_is_checked_against_the_formula(self):
        spec = build(TEX["energy-momentum"], expr="E = sqrt((p*c)**2 + (m*c**2)**2)")
        self.assertTrue(spec["checked"].startswith("agrees with the formula as written"))
        with self.assertRaises(FormulaError) as caught:
            build(TEX["energy-momentum"], expr="E = sqrt((p*c)**2 + (m*c**3)**2)")
        self.assertIn("does not give what the formula says", str(caught.exception))

    def test_a_formula_that_cannot_be_read_needs_an_expression(self):
        with self.assertRaises(Unreadable) as caught:
            build(TEX["schrodinger"])
        self.assertIn("derivative", str(caught.exception))

    def test_a_special_case_is_marked_as_one(self):
        spec = build(
            TEX["stationary schrodinger"],
            expr="E = n**2*pi**2*hbar**2/(2*m*L**2)",
            sets=[{"key": "n", "value": 1, "min": 1, "max": 5, "means": "which level"}, {"key": "L", "value": 1, "min": 0.5, "max": 3}],
        )
        self.assertTrue(spec["case"])
        self.assertTrue(spec["checked"].startswith("not checked"))
        self.assertEqual(spec["output"]["key"], "E")
        self.assertEqual(next(entry for entry in spec["symbols"] if entry["name"] == "n")["means"], "which level")
        self.assertEqual(next(entry for entry in spec["symbols"] if entry["name"] == "hbar")["key"], r"\hbar")

    def test_an_expression_may_not_use_a_name_from_nowhere(self):
        with self.assertRaises(Unreadable) as caught:
            build(TEX["kinetic energy"], expr="E_k = m*v**2/2 + zeta")
        self.assertIn("zeta", str(caught.exception))

    def test_settings_are_checked(self):
        for bad in (["x=1:3:2"], ["x=one"], ["x=1:2"], ["q=1"], ["x=9:-4:4"]):
            with self.subTest(bad), self.assertRaises(FormulaError):
                build(GAUSS, sets=bad)
        with self.assertRaises(FormulaError):
            build(GAUSS, sweep="q")

    def test_a_hint_for_a_symbol_that_is_not_there_is_dropped_and_a_set_wins(self):
        spec = build(GAUSS, hints=[{"key": "q", "value": 3}, {"key": "x", "value": 0, "min": -9, "max": 9}], sets=["x=1:-2:2"])
        x = next(entry for entry in spec["symbols"] if entry["name"] == "x")
        self.assertEqual((x["value"], x["min"], x["max"]), (1.0, -2.0, 2.0))

    def test_test_points_stay_in_range_and_have_values(self):
        spec = build(GAUSS, sets=GAUSS_SETS)
        found = points(spec)
        self.assertEqual(len(found), 8)
        for env in found:
            self.assertFalse(math.isnan(value(tree(spec), env)))
            for entry in spec["symbols"]:
                self.assertTrue(entry["min"] <= env[entry["key"]] <= entry["max"])


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.spec = build(GAUSS, sets=GAUSS_SETS, name="The bell curve")

    def test_page_is_one_file_with_the_card_a_slider_per_symbol_and_the_formula(self):
        page = data(self.spec, "page").decode("utf-8")
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertEqual(page.count('type="range"'), 3)
        self.assertIn("<svg", page)
        self.assertIn("function F(v){return 1/(v.sigma*Math.sqrt(2*Math.PI))", page)
        self.assertNotRegex(page, r'(?:src|href)="https?://(?!scrya\.com)')
        for entry in self.spec["symbols"]:
            self.assertIn(f'data-row="{entry["row"]}" style="--c:{entry["color"]}"', page)
            self.assertIn(f'.bench[data-lit="{entry["row"]}"] .card svg .s{entry["row"]}{{opacity:1}}', page)

    def test_page_shows_a_constant_without_a_slider(self):
        spec = build(TEX["planck law"], constant=["h", "c", "k_B"])
        page = data(spec, "page").decode("utf-8")
        self.assertEqual(page.count('type="range"'), 2)
        self.assertEqual(page.count("a constant: it does not change"), 3)

    def test_page_keeps_a_script_end_out_of_its_data(self):
        spec = build("y=ax", sets=[{"key": "a", "value": 1, "min": 0, "max": 2, "unit": "</script><b>"}])
        page = data(spec, "page").decode("utf-8")
        self.assertEqual(page.count("</script>"), 2)
        self.assertNotIn("<b>", page)

    def test_scene_is_python_that_gives_the_same_numbers(self):
        source = data(self.spec, "scene", file="gauss.py").decode("utf-8")
        compile(source, "gauss.py", "exec")
        self.assertIn("class Bench(m.Scene):", source)
        self.assertIn("manimgx render gauss.py Bench", source)
        # Run the formula it carries, without ManimGX.
        body = source[source.index("def f(v") : source.index("def stroke(")]
        scope = {"math": math}
        exec(body, scope)  # noqa: S102
        self.assertAlmostEqual(scope["f"]({"sigma": 1.0, "x": 0.0, "mu": 0.0}), 0.3989422804014327)
        self.assertTrue(math.isnan(scope["f"]({"sigma": 0.0, "x": 0.0, "mu": 0.0})))
        self.assertIn("'\\\\sigma': \"#ff7eb6\"", source)

    def test_scene_takes_a_python_word_for_a_name(self):
        source = data(build(TEX["de broglie"], solve="p"), "scene").decode("utf-8")
        compile(source, "bench.py", "exec")
        self.assertIn('lambda_ = v["lambda"]', source)

    def test_make_picks_the_kind_from_the_ending(self):
        with tempfile.TemporaryDirectory() as folder:
            for ending in (".html", ".py", ".json"):
                path = make(self.spec, os.path.join(folder, "bell" + ending))
                self.assertTrue(os.path.getsize(path) > 500)
            with open(os.path.join(folder, "bell.json"), encoding="utf-8") as handle:
                self.assertEqual(load(json.load(handle)), self.spec)
            with self.assertRaises(FormulaError):
                make(self.spec, os.path.join(folder, "bell.txt"))


@unittest.skipUnless(importlib.util.find_spec("openpyxl"), "the openpyxl package is not installed")
class SheetTests(unittest.TestCase):
    def book(self, spec):
        import openpyxl

        return openpyxl.load_workbook(io.BytesIO(data(spec, "sheet")))

    def test_sheet_has_a_named_colored_cell_for_each_symbol_and_a_live_formula(self):
        spec = build(GAUSS, sets=GAUSS_SETS)
        book = self.book(spec)
        self.assertEqual(book.sheetnames, ["Bench", "Sweeps", "Check"])
        bench = book["Bench"]
        for offset, entry in enumerate(spec["symbols"]):
            cell = bench.cell(row=6 + offset, column=3)
            self.assertEqual(cell.value, entry["value"])
            self.assertEqual(cell.fill.fgColor.rgb, "FF" + entry["color"].lstrip("#").upper())
            self.assertEqual(book.defined_names[entry["name"] + "_"].attr_text, f"Bench!$C${6 + offset}")
        result = bench.cell(row=10, column=3).value
        self.assertEqual(result, "=1/(sigma_*SQRT(2*PI()))*EXP(-((x_-mu_)^2/(2*sigma_^2)))")
        self.assertEqual(len(bench._charts), 3)
        self.assertEqual(len(bench._images), 1)

    def test_sheet_formulas_give_what_eqlens_gives(self):
        for name, extra in (("gaussian", {"sets": GAUSS_SETS}), ("planck law", {"constant": ["h", "c", "k_B"], "sets": [r"\nu=3e14:1e13:2e15", "T=5000:1000:9000"]}), ("lorentz factor", {})):
            with self.subTest(name):
                spec = build(TEX[name], **extra)
                check = self.book(spec)["Check"]
                n = len(spec["symbols"])
                rows = 0
                for row in check.iter_rows(min_row=4, values_only=True):
                    if row[0] is None:
                        break
                    cells = {f"{chr(65 + i)}{4 + rows}": row[i] for i in range(n)}
                    self.assertTrue(math.isclose(excel(row[n][1:], cells), row[n + 1], rel_tol=1e-12))
                    rows += 1
                self.assertEqual(rows, 8)
                self.assertIn("agree at 8 points", check["B1"].value)

    def test_sweeps_run_each_symbol_across_its_range(self):
        spec = build(GAUSS, sets=GAUSS_SETS)
        sweeps = self.book(spec)["Sweeps"]
        self.assertEqual(sweeps["A2"].value, "=Bench!$D$6+(Bench!$E$6-Bench!$D$6)*0/60")
        self.assertEqual(sweeps["B2"].value, "=IFERROR(1/(A2*SQRT(2*PI()))*EXP(-((x_-mu_)^2/(2*A2^2))),NA())")
        self.assertEqual(sweeps["D62"].value, "=IFERROR(1/(sigma_*SQRT(2*PI()))*EXP(-((C62-mu_)^2/(2*sigma_^2))),NA())")


class CliTests(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--local", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_bench_writes_each_file_and_prints_its_path(self):
        with tempfile.TemporaryDirectory() as folder:
            page, spec, scene = (os.path.join(folder, name) for name in ("g.html", "g.json", "g.py"))
            sets = [arg for item in GAUSS_SETS for arg in ("--set", item)]
            code, out, _err = self.run_cli("--bench", page, "--bench", spec, "--bench", scene, *sets, GAUSS)
            self.assertEqual(code, 0)
            self.assertEqual(out.split(), [page, spec, scene])
            again = os.path.join(folder, "again.html")
            code, out, _err = self.run_cli("--spec", spec, "--bench", again)
            self.assertEqual(code, 0)
            with open(page, "rb") as a, open(again, "rb") as b:
                self.assertEqual(a.read(), b.read())

    def test_bench_says_why_it_cannot_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "s.html")
            code, _out, err = self.run_cli("--bench", path, TEX["schrodinger"])
            self.assertEqual(code, 1)
            self.assertIn("derivative", err)
            self.assertFalse(os.path.exists(path))
            code, _out, err = self.run_cli("--bench", os.path.join(folder, "s.txt"), "y=x")
            self.assertEqual(code, 1)
            self.assertIn(".xlsx, .html, .py, or .json", err)

    def test_solve_and_expr(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "gas.json")
            self.assertEqual(self.run_cli("--bench", path, "--solve", "T", "PV=nRT")[0], 0)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["expr"], "P*V/(n*R)")
            self.assertEqual(self.run_cli("--bench", path, "--expr", "E = sqrt((p*c)**2+(m*c**2)**2)", TEX["energy-momentum"])[0], 0)
            code, _out, err = self.run_cli("--bench", path, "--expr", "E = p*c", TEX["energy-momentum"])
            self.assertEqual(code, 1)
            self.assertIn("does not give what the formula says", err)


class _Response:
    def __init__(self, text):
        self.content = [type("Block", (), {"type": "text", "text": text})()]
        self.stop_reason = "end_turn"


class _Claude:
    def __init__(self, answer):
        self.messages = self
        self.answer = answer
        self.request = None

    def create(self, **request):
        self.request = request
        return _Response(json.dumps(self.answer))


@unittest.skipUnless(importlib.util.find_spec("anthropic"), "the anthropic package is not installed")
class WorkableTests(unittest.TestCase):
    ANSWER = {
        "computable": True,
        "why": "A particle held in a box with hard walls.",
        "expr": "E = n**2*pi**2*hbar**2/(2*m*L**2)",
        "sweep": "L",
        "symbols": [
            {"key": "n", "value": 1, "min": 1, "max": 5, "unit": "", "means": "which level"},
            {"key": "L", "value": 1, "min": 0.5, "max": 3, "unit": "nm", "means": "the width of the box"},
            {"key": "m", "value": 1, "min": 0.5, "max": 2, "unit": "", "means": ""},
            {"key": "zz", "value": 5, "min": 9, "max": 1, "unit": "", "means": ""},
        ],
    }

    def test_claudes_answer_builds_a_bench(self):
        claude = _Claude(self.ANSWER)
        found = workable(TEX["stationary schrodinger"], client=claude)
        self.assertIn("hbar", claude.request["messages"][0]["content"])
        self.assertEqual(claude.request["output_config"]["format"]["type"], "json_schema")
        spec = build(TEX["stationary schrodinger"], expr=found["expr"], sweep=found["sweep"], hints=found["hints"])
        self.assertEqual(spec["sweep"], "L")
        self.assertEqual(next(e for e in spec["symbols"] if e["name"] == "L")["unit"], "nm")
        self.assertTrue(spec["case"])

    def test_no_case_is_an_error(self):
        with self.assertRaises(IntrospectError) as caught:
            workable(TEX["einstein field"], client=_Claude({**self.ANSWER, "computable": False, "why": "It relates tensors."}))
        self.assertIn("It relates tensors", str(caught.exception))


class McpTests(unittest.TestCase):
    def call(self, tool, **arguments):
        answer = handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": tool, "arguments": arguments}})
        return answer["result"]

    def test_handshake_and_tool_list(self):
        answer = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}})
        self.assertEqual(answer["result"]["protocolVersion"], "2025-03-26")
        self.assertIn("tools", answer["result"]["capabilities"])
        newer = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2099-01-01"}})
        self.assertEqual(newer["result"]["protocolVersion"], "2025-06-18")
        self.assertIsNone(handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        tools = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["eqlens_render", "eqlens_inspect", "eqlens_bench"])
        for tool in TOOLS:
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertEqual(tool["inputSchema"]["required"], ["tex"])
        self.assertEqual(handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})["error"]["code"], -32601)
        self.assertEqual(handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope"}})["error"]["code"], -32602)

    def test_stdio_is_one_json_answer_per_line(self):
        lines = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
            "not json",
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        ]
        out = io.BytesIO()
        serve(io.BytesIO(("\n".join(lines) + "\n").encode("utf-8")), out)
        answers = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([answer.get("id") for answer in answers], [1, None, 2])
        self.assertEqual(answers[1]["error"]["code"], -32700)

    def test_render_returns_the_picture_and_its_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "e.png")
            result = self.call("eqlens_render", tex=r"e^{i\pi}+1=0", brief=True, path=path)
            self.assertEqual(result["content"][0]["text"], path)
            self.assertEqual(result["content"][1]["mimeType"], "image/png")
            with open(path, "rb") as handle_:
                self.assertTrue(handle_.read().startswith(b"\x89PNG"))
            bad = self.call("eqlens_render", tex=r"\begin{matrix}a\end{matrix}", path=path)
            self.assertTrue(bad["isError"])

    def test_inspect_says_whether_a_formula_works_out(self):
        found = json.loads(self.call("eqlens_inspect", tex=GAUSS)["content"][0]["text"])
        self.assertTrue(found["works_out"]["as_written"])
        self.assertEqual(found["works_out"]["names"]["sigma"], r"\sigma")
        found = json.loads(self.call("eqlens_inspect", tex=TEX["schrodinger"])["content"][0]["text"])
        self.assertFalse(found["works_out"]["as_written"])
        self.assertIn("derivative", found["works_out"]["why"])
        self.assertEqual(found["works_out"]["names"]["H_hat"], r"\hat{H}")

    def test_bench_writes_files_and_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.call(
                "eqlens_bench",
                tex=GAUSS,
                name="The bell curve",
                symbols=[{"key": "x", "value": 0, "min": -4, "max": 4}, {"key": "mu", "value": 0, "min": -2, "max": 2}, {"key": r"\sigma", "value": 1, "min": 0.3, "max": 3, "means": "how wide the bell is"}],
                outputs=["html", "scene", "spec"],
                out_dir=folder,
            )
            self.assertNotIn("isError", result)
            report = json.loads(result["content"][0]["text"])
            self.assertEqual(sorted(os.listdir(folder)), ["the-bell-curve.html", "the-bell-curve.json", "the-bell-curve_scene.py"])
            self.assertAlmostEqual(report["result_at_start"], 0.3989422804014327)
            self.assertIn("manimgx render", report["render_scene_with"])
            self.assertFalse(report["one_case_only"])
            refused = self.call("eqlens_bench", tex=TEX["schrodinger"], out_dir=folder)
            self.assertTrue(refused["isError"])
            self.assertIn("derivative", refused["content"][0]["text"])



class StepTests(unittest.TestCase):
    TEX = r"E_n=\hbar\omega\left(n+\frac{1}{2}\right)"

    def spec(self, n="n=0:0:10/1"):
        from eqlens.bench.spec import build

        return build(self.TEX, constant=["hbar"], sets=[r"\omega=1e15:1e14:5e15", n])

    def test_a_stepped_symbol_is_worked_out_on_its_steps_only(self):
        from eqlens.bench.spec import curve, load

        spec = self.spec()
        n = next(entry for entry in spec["symbols"] if entry["key"] == "n")
        self.assertEqual(n["step"], 1.0)
        xs, ys = curve(spec, "n")
        self.assertEqual(xs, [float(i) for i in range(11)])
        self.assertEqual(len(ys), 11)
        self.assertNotIn("step", next(entry for entry in spec["symbols"] if entry["key"] == r"\omega"))
        again = load(spec)
        self.assertEqual(next(entry for entry in again["symbols"] if entry["key"] == "n")["step"], 1.0)

    def test_the_value_and_the_top_land_on_a_step(self):
        n = next(entry for entry in self.spec("n=2.4:0:9.5/1")["symbols"] if entry["key"] == "n")
        self.assertEqual((n["value"], n["max"]), (2.0, 9.0))

    def test_a_bad_step_is_refused(self):
        from eqlens.engine import FormulaError

        for bad in ("n=0:0:10/0", "n=0:0:10/x", "n=0:0:10/0.001", "n=0:0:10/50"):
            with self.subTest(bad), self.assertRaises(FormulaError):
                self.spec(bad)

    def test_the_page_steps_its_slider_and_the_card_draws_dots(self):
        from eqlens.bench import data
        from eqlens.render import render_html

        page = data(self.spec(), "page").decode("utf-8")
        self.assertIn('step="1.0"', page)
        self.assertIn('"step":1.0', page.replace(" ", ""))
        card = render_html(self.TEX, legend=True, define=["n=the level"], constant=["hbar"], sets=[r"\omega=1e15:1e14:5e15", "n=0:0:10/1"])
        cards = json.loads(re.search(r'class="eqlens-pops">(.*?)</script>', card, re.S).group(1))
        n = next(item for item in cards if item["g"] == "n")
        self.assertEqual((n["st"], len(n["ys"])), (1.0, 11))


if __name__ == "__main__":
    unittest.main()
