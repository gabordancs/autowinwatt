"""Small PySide6 two-panel review application; imports are lazy for headless use."""
from __future__ import annotations

from pathlib import Path

from .domain import ReviewStatus, numeric_value
from .pdf_evidence import render_viewport
from .persistence import ReviewStore


def run_gui(store: ReviewStore, pdf_root: Path, reviewer: str) -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPixmap, QShortcut, QKeySequence
    from PySide6.QtWidgets import QApplication, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget

    class ReviewWindow(QMainWindow):
        def __init__(self):
            super().__init__(); self.setWindowTitle("WebWatt E2E – PDF evidence review"); self.resize(1440, 900)
            self.items = store.list(); self.index = 0
            left = QWidget(); form = QFormLayout(left)
            self.progress = QLabel(); self.meta = QLabel(); self.machine = QLabel(); self.value = QLineEdit(); self.note = QTextEdit(); self.status = QComboBox(); self.status.addItems([x.value for x in ReviewStatus])
            form.addRow("Haladás", self.progress); form.addRow("Objektum / mező", self.meta); form.addRow("Gépi érték", self.machine); form.addRow("Felülvizsgált érték", self.value); form.addRow("Státusz", self.status); form.addRow("Megjegyzés", self.note)
            buttons = QHBoxLayout()
            for title, state in (("Elfogadás [A]", ReviewStatus.ACCEPTED), ("Felülírás [E]", ReviewStatus.EDITED), ("Elutasítás [R]", ReviewStatus.REJECTED), ("Nem azonosítható [U]", ReviewStatus.UNRESOLVED)):
                button=QPushButton(title); button.clicked.connect(lambda checked=False, s=state: self.apply(s)); buttons.addWidget(button)
            previous=QPushButton("Előző"); previous.clicked.connect(lambda: self.move(-1)); following=QPushButton("Következő"); following.clicked.connect(lambda: self.move(1)); buttons.addWidget(previous); buttons.addWidget(following); form.addRow(buttons)
            right=QWidget(); right_layout=QVBoxLayout(right); self.image=QLabel("PDF evidence betöltése..."); self.image.setAlignment(Qt.AlignCenter); self.image.setMinimumSize(700, 700); self.pdf_state=QLabel(); right_layout.addWidget(self.image); right_layout.addWidget(self.pdf_state)
            split=QSplitter(); split.addWidget(left); split.addWidget(right); split.setStretchFactor(1, 1); self.setCentralWidget(split)
            QShortcut(QKeySequence("A"), self, activated=lambda: self.apply(ReviewStatus.ACCEPTED)); QShortcut(QKeySequence("E"), self, activated=lambda: self.apply(ReviewStatus.EDITED)); QShortcut(QKeySequence("R"), self, activated=lambda: self.apply(ReviewStatus.REJECTED)); QShortcut(QKeySequence("U"), self, activated=lambda: self.apply(ReviewStatus.UNRESOLVED)); QShortcut(QKeySequence("Left"), self, activated=lambda: self.move(-1)); QShortcut(QKeySequence("Right"), self, activated=lambda: self.move(1)); QShortcut(QKeySequence("Ctrl+S"), self, activated=self.refresh)
            self.refresh()

        def refresh(self):
            self.items=store.list()
            if not self.items: return
            self.index=max(0,min(self.index,len(self.items)-1)); item=self.items[self.index]
            self.progress.setText(f"{self.index+1} / {len(self.items)}"); self.meta.setText(f"{item.entity_type} · {item.entity_id} · {item.field_name}"); self.machine.setText(str(item.machine_value)); self.value.setText("" if item.reviewed_value is None else str(item.reviewed_value)); self.note.setPlainText(item.note or ""); self.status.setCurrentText(item.status.value)
            pdf = self._find_pdf(item.evidence.source_pdf)
            if not pdf: self.image.setText("Forrás-PDF nem található.\n" + (item.evidence.source_pdf or "nincs PDF-forrás")); self.pdf_state.setText(item.evidence.location_status); return
            try:
                data, viewport=render_viewport(pdf,item.evidence); image=QImage.fromData(data,"PNG"); self.image.setPixmap(QPixmap.fromImage(image).scaled(self.image.size(),Qt.KeepAspectRatio,Qt.SmoothTransformation)); self.pdf_state.setText(f"{pdf.name}, oldal {viewport.page}; {item.evidence.location_status}; kivágat {viewport.crop}")
            except Exception as exc: self.image.setText(f"PDF megjelenítési hiba: {exc}")

        def _find_pdf(self, source: str | None) -> Path | None:
            if not source: return None
            key=source.replace("É", "E").replace("-", "").replace(" ", "").split("+")[0].casefold()
            for path in pdf_root.glob("*.pdf"):
                normalized=path.name.replace("É", "E").replace("-", "").replace(" ", "").casefold()
                if key in normalized: return path
            return None

        def apply(self, state: ReviewStatus):
            item=self.items[self.index]
            value=self.value.text().strip() or None
            try:
                if state is ReviewStatus.EDITED: numeric_value(value,item.unit)
                store.transition(item.candidate_id,state,reviewer=reviewer,reviewed_value=value,note=self.note.toPlainText() or None)
                self.refresh()
            except ValueError as exc: QMessageBox.warning(self,"Érvénytelen érték",str(exc))

        def move(self, direction: int): self.index=max(0,min(self.index+direction,len(self.items)-1)); self.refresh()

    app=QApplication.instance() or QApplication([]); window=ReviewWindow(); window.show(); return app.exec()
