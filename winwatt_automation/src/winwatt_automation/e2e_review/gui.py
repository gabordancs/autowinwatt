"""Small PySide6 two-panel review application; imports are lazy for headless use."""
from __future__ import annotations

from pathlib import Path

from .domain import ReviewStatus, numeric_value
from .pdf_evidence import render_full_page
from .persistence import ReviewStore
from .wall_overlay import WallOverlay, layout_outside_labels


def run_gui(store: ReviewStore, pdf_root: Path, reviewer: str, *, wall_overlay_path: Path | None = None) -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap, QShortcut, QKeySequence
    from PySide6.QtWidgets import QApplication, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSplitter, QTextEdit, QVBoxLayout, QWidget

    class PdfScrollArea(QScrollArea):
        """Normal wheel scroll; Ctrl+wheel is mouse-centred zoom."""
        def __init__(self, zoom_callback):
            super().__init__(); self.zoom_callback=zoom_callback
        def wheelEvent(self, event):
            if event.modifiers() & Qt.ControlModifier:
                self.zoom_callback(1.2 if event.angleDelta().y() > 0 else 1/1.2, event.position().toPoint())
                event.accept(); return
            super().wheelEvent(event)

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
            right=QWidget(); right_layout=QVBoxLayout(right); self.zoom=1.5; self.current_pdf=None; self.current_evidence=None; self.current_viewport=None; self.wall_overlay=WallOverlay.load(wall_overlay_path) if wall_overlay_path else None
            self.image=QLabel("PDF evidence betöltése..."); self.image.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.pdf_scroll=PdfScrollArea(self.zoom_at_mouse); self.pdf_scroll.setWidget(self.image); self.pdf_scroll.setWidgetResizable(False); self.pdf_scroll.setAlignment(Qt.AlignCenter)
            toolbar=QHBoxLayout(); zoom_out=QPushButton("−"); zoom_out.clicked.connect(lambda: self.zoom_at_mouse(1/1.2)); zoom_in=QPushButton("+"); zoom_in.clicked.connect(lambda: self.zoom_at_mouse(1.2)); fit_context=QPushButton("Evidence nézet"); fit_context.clicked.connect(self.fit_context); fit_page=QPushButton("Teljes oldal"); fit_page.clicked.connect(self.fit_page)
            for control in (zoom_out, zoom_in, fit_context, fit_page): toolbar.addWidget(control)
            toolbar.addStretch(); self.pdf_state=QLabel(); right_layout.addLayout(toolbar); right_layout.addWidget(self.pdf_scroll); right_layout.addWidget(self.pdf_state)
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
                self.current_pdf=pdf; self.current_evidence=item.evidence; self.zoom=1.5; self.render_page(center_evidence=True)
            except Exception as exc: self.image.setText(f"PDF megjelenítési hiba: {exc}")

        def render_page(self, *, center_evidence: bool=False):
            if not self.current_pdf or not self.current_evidence: return
            data, viewport=render_full_page(self.current_pdf,self.current_evidence,zoom=self.zoom); self.current_viewport=viewport
            image=QImage.fromData(data,"PNG"); pixmap=QPixmap.fromImage(image); labels=self.wall_overlay.labels_for_pdf(self.current_pdf.name) if self.wall_overlay else []
            if labels: self._draw_wall_overlay(pixmap,labels)
            self.image.setPixmap(pixmap); self.image.resize(image.size())
            suffix=f" | {len(labels)} faljelölt" if labels else ""
            self.pdf_state.setText(f"{self.current_pdf.name}, oldal {viewport.page}; {self.current_evidence.location_status}; {self.zoom:.0%}{suffix}. Görgetés: pásztázás, Ctrl+görgő: zoom.")
            if center_evidence and self.current_evidence.evidence_bbox:
                x0,y0,x1,y1=self.current_evidence.evidence_bbox; center_x=(x0+x1)/2*self.zoom; center_y=(y0+y1)/2*self.zoom
                self.pdf_scroll.horizontalScrollBar().setValue(max(0,int(center_x-self.pdf_scroll.viewport().width()/2))); self.pdf_scroll.verticalScrollBar().setValue(max(0,int(center_y-self.pdf_scroll.viewport().height()/2)))

        def _draw_wall_overlay(self, pixmap, labels):
            painter=QPainter(pixmap); painter.setRenderHint(QPainter.Antialiasing); font=QFont("Arial",max(7,int(8*self.zoom))); painter.setFont(font)
            metrics=painter.fontMetrics(); leading=metrics.height()+2
            placed=layout_outside_labels(labels,pixmap.width(),pixmap.height(),line_height=leading,width_for_lines=lambda lines:max(metrics.horizontalAdvance(line) for line in lines))
            for item in placed:
                # Leader line ends at the inner edge of the side label. Its
                # anchor remains inside the actual room, while the blue box is
                # kept outside the usable plan area.
                end_x=item.rect_x+item.width if item.side=="left" else item.rect_x
                end_y=min(max(item.anchor_y,item.rect_y+6),item.rect_y+item.height-6)
                painter.setPen(QPen(QColor("#075a87"),max(1,int(self.zoom)))); painter.drawLine(int(item.anchor_x),int(item.anchor_y),int(end_x),int(end_y))
                painter.setBrush(QColor("#075a87")); painter.drawEllipse(int(item.anchor_x-2*self.zoom),int(item.anchor_y-2*self.zoom),max(3,int(4*self.zoom)),max(3,int(4*self.zoom)))
                painter.setPen(QPen(QColor("#075a87"))); painter.setBrush(QColor(0,96,145,235)); painter.drawRoundedRect(int(item.rect_x),int(item.rect_y),int(item.width),int(item.height),5,5); painter.setPen(QPen(QColor("white")))
                for index,line in enumerate(item.label.lines): painter.drawText(int(item.rect_x+6),int(item.rect_y+leading*(index+1)),line)
            painter.end()

        def zoom_at_mouse(self, factor: float, position=None):
            if not self.current_pdf: return
            old=self.zoom; self.zoom=max(0.35,min(6.0,self.zoom*factor))
            if position is None: self.render_page(center_evidence=False); return
            h=self.pdf_scroll.horizontalScrollBar(); v=self.pdf_scroll.verticalScrollBar(); point_x=(h.value()+position.x())/old; point_y=(v.value()+position.y())/old
            self.render_page(center_evidence=False); h.setValue(max(0,int(point_x*self.zoom-position.x()))); v.setValue(max(0,int(point_y*self.zoom-position.y())))

        def fit_page(self):
            if not self.current_pdf: return
            # PDF points at 72 dpi; a conservative available-width fit is enough
            # and preserves a scrollable page for tall plans.
            self.zoom=max(0.35,min(2.0,self.pdf_scroll.viewport().width()/600)); self.render_page(center_evidence=False)

        def fit_context(self):
            if not self.current_evidence: return
            self.zoom=1.5; self.render_page(center_evidence=True)

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
