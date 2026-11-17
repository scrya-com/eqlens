"""The bench as a workbook: a cell for every symbol, the formula as a live cell formula, and a chart for each symbol.

Needs ``openpyxl`` (``pip install 'eqlens[bench]'``). The workbook holds
formulas, not their answers: Excel, LibreOffice, Numbers, and Google Sheets
work them out when the file is opened.

Three sheets. **Bench** has the drawing, one row per symbol with its value in
the symbol's ledger color, the result, and the charts. **Sweeps** has the
numbers the charts draw: for each symbol, the result as that symbol alone runs
across its range. **Check** has the formula worked out at a few fixed points
next to the answers eqlens got for the same points, so a reader can see the
sheet's formula is the right one.
"""

from __future__ import annotations

import io
import math

from eqlens.bench.expr import to_excel
from eqlens.bench.spec import points, tree
from eqlens.engine import FormulaError

STEPS = 60
_HEAD = "FF12141A"
_INK = "FFF2F2F7"


def _openpyxl():
    try:
        import openpyxl
    except ImportError as exc:
        raise FormulaError("an .xlsx bench needs the openpyxl package: pip install 'eqlens[bench]'") from exc
    return openpyxl


def _fill(color: str) -> str:
    return "FF" + color.lstrip("#").upper()


def cell_name(entry: dict) -> str:
    """A defined name for a symbol's cell. The underscore keeps ``c`` and ``r`` and ``x1`` from being read as cells."""
    return entry["name"].rstrip("_") + "_"


def write(spec: dict, card_png: bytes | None = None) -> bytes:
    """The workbook as bytes. ``card_png`` is the drawing of the formula, placed beside the table."""
    openpyxl = _openpyxl()
    from openpyxl.chart import Reference, ScatterChart, Series
    from openpyxl.chart.marker import Marker
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.workbook.defined_name import DefinedName
    from openpyxl.worksheet.datavalidation import DataValidation

    node = tree(spec)
    symbols = spec["symbols"]
    output = spec["output"]
    moving = [entry for entry in symbols if entry["role"] != "constant"]
    book = openpyxl.Workbook()
    bench = book.active
    bench.title = "Bench"
    sweeps = book.create_sheet("Sweeps")
    check = book.create_sheet("Check")

    bold = Font(bold=True)
    dim = Font(color="FF6E7681")
    head_fill = PatternFill("solid", fgColor=_HEAD)
    head_font = Font(bold=True, color=_INK)

    # ---- Bench: the table of symbols
    bench["A1"] = spec["name"] or "eqlens bench"
    bench["A1"].font = Font(bold=True, size=14)
    bench["A2"] = f"{output['name']} = {spec['expr']}"
    bench["A3"] = spec["about"] or ("One case of the formula." if spec.get("case") else "")
    bench["A3"].font = dim
    top = 5
    for column, title in enumerate(("Symbol", "Say", "Value", "From", "To", "Unit", "Means"), start=1):
        cell = bench.cell(row=top, column=column, value=title)
        cell.font, cell.fill = head_font, head_fill
    where: dict[str, int] = {}
    for offset, entry in enumerate(symbols, start=1):
        row = top + offset
        where[entry["key"]] = row
        bench.cell(row=row, column=1, value=entry["shown"]).font = bold
        bench.cell(row=row, column=2, value=entry["says"] or entry["name"])
        cell = bench.cell(row=row, column=3, value=entry["value"])
        cell.fill = PatternFill("solid", fgColor=_fill(entry["color"]))
        cell.font = Font(bold=True, color="FF12141A")
        if entry["role"] == "constant":
            bench.cell(row=row, column=4, value="constant").font = dim
        else:
            bench.cell(row=row, column=4, value=entry["min"])
            bench.cell(row=row, column=5, value=entry["max"])
            rule = DataValidation(
                type="decimal", operator="between", formula1=f"$D${row}", formula2=f"$E${row}",
                errorStyle="warning", showErrorMessage=True,
                errorTitle="Outside the range", error=f"{entry['shown']} is meant to stay between From and To.",
            )
            bench.add_data_validation(rule)
            rule.add(cell)
        bench.cell(row=row, column=6, value=entry["unit"])
        bench.cell(row=row, column=7, value=entry["means"])
        book.defined_names[cell_name(entry)] = DefinedName(cell_name(entry), attr_text=f"Bench!$C${row}")

    result_row = top + len(symbols) + 2
    names = {entry["key"]: cell_name(entry) for entry in symbols}
    bench.cell(row=result_row, column=1, value=output["shown"]).font = bold
    bench.cell(row=result_row, column=2, value=output["says"] or "result")
    result = bench.cell(row=result_row, column=3, value="=" + to_excel(node, lambda key: names[key]))
    result.fill = PatternFill("solid", fgColor=_fill(output["color"]))
    result.font = Font(bold=True, color="FF12141A")
    bench.cell(row=result_row, column=6, value=output["unit"])
    bench.cell(row=result_row, column=7, value=output["means"])
    bench.cell(row=result_row + 1, column=1, value="Worked out as").font = dim
    bench.cell(row=result_row + 1, column=3, value=spec["expr"]).font = dim
    bench.cell(row=result_row + 2, column=1, value="Checked").font = dim
    bench.cell(row=result_row + 2, column=3, value="=Check!B1").font = dim
    bench.cell(row=result_row + 3, column=1, value="Change a colored value and the result and every chart follow.").font = dim
    for column, width in zip("ABCDEFG", (14, 16, 16, 12, 12, 16, 46)):
        bench.column_dimensions[column].width = width
    bench["C" + str(result_row)].alignment = Alignment(horizontal="right")

    if card_png:
        try:
            from openpyxl.drawing.image import Image

            picture = Image(io.BytesIO(card_png))
            scale = min(1.0, 520 / picture.width)
            picture.width, picture.height = int(picture.width * scale), int(picture.height * scale)
            bench.add_image(picture, "I1")
        except ImportError:
            # openpyxl needs Pillow to place a picture. The sheet is whole without it.
            pass

    # ---- Sweeps: for each symbol, the result as it alone runs from From to To
    for index, entry in enumerate(moving):
        column = 1 + 2 * index
        x_col, y_col = get_column_letter(column), get_column_letter(column + 1)
        sweeps.cell(row=1, column=column, value=entry["shown"]).font = bold
        sweeps.cell(row=1, column=column + 1, value=f"{output['shown']} as {entry['shown']} changes").font = bold
        row = where[entry["key"]]
        for step in range(STEPS + 1):
            at = 2 + step
            sweeps.cell(row=at, column=column, value=f"=Bench!$D${row}+(Bench!$E${row}-Bench!$D${row})*{step}/{STEPS}")
            formula = to_excel(node, lambda key: f"{x_col}{at}" if key == entry["key"] else names[key])
            sweeps.cell(row=at, column=column + 1, value=f"=IFERROR({formula},NA())")
        sweeps.column_dimensions[x_col].width = 14
        sweeps.column_dimensions[y_col].width = 22

    # ---- Bench: a chart for each symbol, the swept one large
    order = sorted(range(len(moving)), key=lambda i: moving[i]["key"] != spec["sweep"])
    anchor_row = result_row + 6
    small = 0
    for position, index in enumerate(order):
        entry = moving[index]
        column = 1 + 2 * index
        chart = ScatterChart()
        chart.style = 13
        chart.title = f"{output['shown']} as {entry['shown']} changes"
        chart.x_axis.title = entry["shown"] + (f" ({entry['unit']})" if entry["unit"] else "")
        chart.y_axis.title = output["shown"] + (f" ({output['unit']})" if output["unit"] else "")
        chart.legend = None
        # openpyxl 3.1 marks axes as deleted unless told otherwise, and Excel then draws none.
        chart.x_axis.delete = False
        chart.y_axis.delete = False
        xs = Reference(sweeps, min_col=column, min_row=2, max_row=STEPS + 2)
        ys = Reference(sweeps, min_col=column + 1, min_row=2, max_row=STEPS + 2)
        line = Series(ys, xs, title=entry["shown"])
        line.marker = Marker(symbol="none")
        line.graphicalProperties.line.solidFill = entry["color"].lstrip("#").upper()
        line.graphicalProperties.line.width = 28000
        line.smooth = False
        chart.series.append(line)
        # Where the bench stands now.
        here_x = Reference(bench, min_col=3, min_row=where[entry["key"]])
        here_y = Reference(bench, min_col=3, min_row=result_row)
        here = Series(here_y, here_x, title="now")
        here.marker = Marker(symbol="circle", size=9)
        here.marker.graphicalProperties.solidFill = "12141A"
        here.graphicalProperties.line.noFill = True
        chart.series.append(here)
        if position == 0:
            chart.width, chart.height = 24.0, 11.0
            bench.add_chart(chart, f"A{anchor_row}")
        else:
            chart.width, chart.height = 12.0, 7.0
            bench.add_chart(chart, f"{'AE'[small % 2]}{anchor_row + 23 + 15 * (small // 2)}")
            small += 1

    # ---- Check: the sheet's formula and eqlens's answer at the same points
    check["A1"] = "The sheet and eqlens"
    check["A1"].font = bold
    tests = points(spec)
    first = 4
    last = first + len(tests) - 1
    for column, entry in enumerate(symbols, start=1):
        cell = check.cell(row=3, column=column, value=entry["shown"])
        cell.font, cell.fill = head_font, head_fill
    n = len(symbols)
    for column, title in enumerate(("the sheet says", "eqlens says", "apart by"), start=n + 1):
        cell = check.cell(row=3, column=column, value=title)
        cell.font, cell.fill = head_font, head_fill
        check.column_dimensions[get_column_letter(column)].width = 18
    sheet_col, ours_col, gap_col = (get_column_letter(n + i) for i in (1, 2, 3))
    env_cols = {entry["key"]: get_column_letter(i) for i, entry in enumerate(symbols, start=1)}
    from eqlens.bench.expr import value

    for offset, env in enumerate(tests):
        row = first + offset
        for column, entry in enumerate(symbols, start=1):
            check.cell(row=row, column=column, value=env[entry["key"]])
        check[f"{sheet_col}{row}"] = "=" + to_excel(node, lambda key: f"{env_cols[key]}{row}")
        answer = value(node, env)
        check[f"{ours_col}{row}"] = None if math.isnan(answer) else answer
        check[f"{gap_col}{row}"] = f"=ABS({sheet_col}{row}-{ours_col}{row})/MAX(ABS({ours_col}{row}),1E-300)"
    if tests:
        check["B1"] = f'=IF(MAX({gap_col}{first}:{gap_col}{last})<1E-9,"agree at {len(tests)} points","DIFFER: see the Check sheet")'
    else:
        check["B1"] = "no point in these ranges has a real value"
    check.column_dimensions["A"].width = 22
    check.column_dimensions["B"].width = 26

    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
