"""Create a source-preserving visual audit PDF for the Délceg WWP model."""
from __future__ import annotations

import io
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


TEST = Path(r"C:\Users\Admin\Documents\GitHub\autowinwatt\test")
OUT = TEST / "Delceg_56_hatarolo_szerkezet_v6_XY_kotelezo_falgeometria.pdf"
MODEL = Path(r"C:\Users\Admin\Documents\GitHub\autowinwatt\winwatt_automation\data\certificate_builds\delceg\v2_two_buildings_review\delceg_two_buildings_model.json")
FONT = r"C:\Windows\Fonts\arial.ttf"
FONT_BOLD = r"C:\Windows\Fonts\arialbd.ttf"


def tag(c: canvas.Canvas, x: float, y: float, text: str) -> None:
    lines = text.split("\n")
    font_size = 6.4 if len(lines) > 3 else 8
    leading = 8 if len(lines) > 3 else 10
    width = max(pdfmetrics.stringWidth(line, "Arial", font_size) for line in lines) + 8
    height = len(lines) * leading + 6
    c.setFillColor(colors.Color(0.0, 0.38, 0.56, alpha=0.92))
    c.roundRect(x - width / 2, y - height / 2, width, height, 3, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Arial", font_size)
    for index, line in enumerate(lines):
        c.drawCentredString(x, y + height / 2 - leading + 1 - index * leading, line)


def overlay(width: float, height: float, labels: list[tuple[float, float, str]]) -> PdfReader:
    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=(width, height))
    for x, y, label in labels:
        tag(c, x, y, label)
    c.save()
    stream.seek(0)
    return PdfReader(stream)


def px(page: object, x: float, y: float) -> tuple[float, float]:
    """Map the known A0 plan PNG coordinate system to PDF coordinates."""
    width, height = float(page.mediabox.width), float(page.mediabox.height)
    return x * width / 2526, height - y * height / 3572


def boundary_code(boundary: dict) -> str:
    name = boundary["structure"]
    for code in ("R1B", "R14", "R15", "R16", "R7", "R6", "R5"):
        if f" {code} " in f" {name} ":
            return code
    return "A"


def xy(boundary: dict) -> str:
    """Native WinWatt operands; walls use plan length × room height."""
    return f"{float(boundary.get('x_m', boundary['area_m2'])):.2f}×{float(boundary.get('y_m', 1)):.2f}"


def room_label(room_code: str, model: dict) -> str:
    room = next(item for item in model["rooms"] if item["name"].split(" - ", 1)[0] == room_code)
    boundaries = [item for item in model["boundaries"] if item["room"] == room["name"]]
    preferred = {"R14": 0, "R6": 0, "R1B": 1, "R7": 1, "R5": 2, "R15": 2, "R16": 2}
    boundaries.sort(key=lambda item: (preferred.get(boundary_code(item), 9), boundary_code(item)))
    lines = [f"{room_code} | A={room['area_m2']:.2f} m² | h={room['height_m']:.2f} m"]
    for item in boundaries:
        if item.get("slope") == "függőleges" and "x_m" not in item:
            lines.append(f"{boundary_code(item)}: X×Y=ELLENŐRZENDŐ")
        else:
            lines.append(f"{boundary_code(item)}: X×Y={xy(item)}")
    return "\n".join(lines)


def page_labels(page: object, spec: list[tuple[float, float, str]], model: dict) -> list[tuple[float, float, str]]:
    return [(*px(page, x, y), room_label(code, model)) for x, y, code in spec]


def summary_page() -> object:
    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=(841.89, 1190.55))
    c.setFont("Arial-Bold", 22)
    c.drawString(48, 1130, "Délceg utca 56 - WinWatt modellvizsgálat")
    c.setFont("Arial", 11)
    c.drawString(48, 1105, "Cél: helyiségek és energetikailag releváns határoló szerkezetek visszakövethető ellenőrzése.")
    c.setStrokeColor(colors.HexColor("#16708a")); c.setLineWidth(2); c.line(48, 1094, 794, 1094)
    rows = [
        ("Források", "É02 földszint, É02B tetőtér, É02C pince, É03 metszetek; 2018-as tanúsítvány a meglévő zónához."),
        ("Feldolgozás", "Helyi PDF-szöveg- és tervlapolvasás; terv szerinti helyiségterületek; determinisztikus határoló-generálás."),
        ("WinWatt rögzítés", "32 bites WinWatt import XML -> üres projekt -> mentés -> bezárás/újranyitás -> natív XML-visszaexport."),
        ("Visszaellenőrzés", "2 épület, 29 helyiség, 12 szerkezettípus, 79 határoló; területeltérés 0,00 m²."),
        ("Fontos korlát", "A01 aggregált meglévő zóna. Az ELLENŐRZENDŐ R5-címke azt jelenti: nincs még tervi X=hossz, Y=magasság falgeometria; WWP-import tiltott."),
    ]
    y = 1050
    for title, text in rows:
        c.setFont("Arial-Bold", 11); c.setFillColor(colors.HexColor("#124f65")); c.drawString(48, y, title)
        c.setFont("Arial", 10); c.setFillColor(colors.black)
        words = text.split(); line = ""; yy = y
        for word in words:
            test = (line + " " + word).strip()
            if pdfmetrics.stringWidth(test, "Arial", 10) > 630:
                c.drawString(174, yy, line); yy -= 14; line = word
            else: line = test
        c.drawString(174, yy, line); y = yy - 27
    c.setFont("Arial-Bold", 14); c.drawString(48, y, "Jelölési elv az alaprajzokon")
    y -= 25
    c.setFont("Arial", 10)
    c.drawString(48, y, "A kék címke első sora: helyiségkód, WinWattban rögzített alapterület (A) és belmagasság (h).")
    y -= 20
    c.drawString(48, y, "A további sorok: szerkezeti kód és a ténylegesen rögzített X×Y méret. Falnál X=hossz, Y=magasság, A=X×Y.")
    y -= 20
    c.drawString(48, y, "R14 = talajon fekvő padló; R1B = új tető; R7 = ferde tető; R5 = új külső fal; R6 = födém; R15/R16 = pincefal.")
    y -= 34
    c.setFont("Arial-Bold", 14); c.drawString(48, y, "Szerkezeti döntések")
    y -= 24
    decisions = [
        "Külső fal csak olyan helyiséghez került, amely a terv külső kontúrját érinti; belső válaszfal nem lett hamisan külső hőhatároló.",
        "Minden fűtött helyiséghez alsó és felső hőhatároló került. A tetőtéri helyiségek ferde tetője R7, a pince falai R15/R16.",
        "Az R1B/R5/R6/R7/R14/R15 U-értékei előzetes rétegrendi számítások. Anyagkatalógus-rögzítés és nyílászáró-termékadat még külön ellenőrzési lépés.",
    ]
    c.setFont("Arial", 10)
    for item in decisions:
        c.drawString(58, y, "•")
        words=item.split(); line=""; yy=y
        for word in words:
            test=(line+" "+word).strip()
            if pdfmetrics.stringWidth(test,"Arial",10)>680:
                c.drawString(75,yy,line);yy-=14;line=word
            else: line=test
        c.drawString(75,yy,line); y=yy-22
    c.setFillColor(colors.HexColor("#555555")); c.setFont("Arial", 8)
    c.drawString(48, 45, "Kék címkék tájékoztató ellenőrző jelölések; az eredeti tervgeometria változatlanul a háttérben marad.")
    c.save(); stream.seek(0)
    return PdfReader(stream).pages[0]


def main() -> None:
    pdfmetrics.registerFont(TTFont("Arial", FONT)); pdfmetrics.registerFont(TTFont("Arial-Bold", FONT_BOLD))
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    sources = [
        (TEST / "É02_TERVEZETT FÖLDSZINTI ALAPRAJZ_végl.pdf", [
            (850, 2400, "B03"), (1290, 2400, "B04"), (800, 1740, "B05a"), (1195, 1930, "B05b"),
            (1390, 1440, "B05c"), (1510, 1550, "B05d"), (980, 1570, "B05e"), (1460, 2020, "B06"),
            (1080, 1830, "B07a"), (1080, 1460, "B07b"), (800, 1530, "B07c"), (700, 1150, "B08"),
            (1240, 980, "B09"), (1470, 870, "B10a"), (740, 1680, "B10b"), (1130, 1570, "B10c"),
        ]),
        (TEST / "É02B_TERVEZETT TETŐTÉRI ALAPRAJZ_végl.pdf", [
            (1420, 1320, "B11a"), (1430, 1470, "B11b"), (1450, 2050, "B11c"), (820, 1430, "B12"),
            (1320, 930, "B13"), (810, 2050, "B14"), (1350, 2130, "B15"), (820, 2530, "B16"),
            (1070, 1180, "B17"), (1360, 1770, "B18"),
        ]),
        (TEST / "É02C_TERVEZETT PINCESZINTI ALAPRAJZ_végl.pdf", [
            (1290, 1400, "B01"), (1400, 1930, "B02"),
        ]),
    ]
    writer = PdfWriter(); writer.add_page(summary_page())
    for path, labels in sources:
        page = PdfReader(path).pages[0]
        page.merge_page(overlay(float(page.mediabox.width), float(page.mediabox.height), page_labels(page, labels, model)).pages[0])
        writer.add_page(page)
    with OUT.open("wb") as stream: writer.write(stream)
    print(OUT)


if __name__ == "__main__":
    main()
