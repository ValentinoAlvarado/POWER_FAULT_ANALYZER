"""Dockable browser for source-pinned QElectroTech drawing candidates."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from power_fault_analyzer.infrastructure.symbols.qet_catalog import (
    QETSymbolCatalog,
    load_qet_symbol_catalog,
)
from power_fault_analyzer.infrastructure.symbols.qet_elmt import QETSymbolError, SymbolDefinition
from power_fault_analyzer.interfaces.desktop.icon_theme import engineering_icon
from power_fault_analyzer.interfaces.desktop.workbench.qet_symbol_item import (
    QETSymbolItem,
    UnsupportedQETPrimitiveError,
)


class QETSymbolBrowser(QWidget):
    """Browse and preview actual imported QET files; never invents substitutes."""

    symbol_selected = Signal(str)
    insert_requested = Signal(str, float)

    def __init__(
        self,
        repository_root: str | Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository_root = Path(repository_root).resolve()
        self.manifest_path = (
            self.repository_root / "RESEARCH" / "qelectrotech-symbol-candidates.csv"
        )
        self.asset_root = self.repository_root / "assets" / "third_party" / "qelectrotech-elements"
        self.catalog: QETSymbolCatalog | None = None
        self._definitions_by_asset_id: dict[str, SymbolDefinition] = {}
        self._preview_item: QETSymbolItem | None = None
        self._preview_rotation = 0.0

        self.search = QLineEdit()
        self.search.setObjectName("SymbolSearch")
        self.search.setPlaceholderText("Search source symbols…")
        self.search.textChanged.connect(self._filter_symbols)

        self.asset_list = QListWidget()
        self.asset_list.setObjectName("QETAssetList")
        self.asset_list.setMinimumWidth(145)
        self.asset_list.setUniformItemSizes(True)
        self.asset_list.currentItemChanged.connect(self._selection_changed)
        self.asset_list.itemDoubleClicked.connect(lambda _item: self._request_insert())

        self.preview_scene = QGraphicsScene(self)
        self.preview_scene.setBackgroundBrush(QBrush(QColor("#FFFFFF")))
        self.preview = QGraphicsView(self.preview_scene)
        self.preview.setObjectName("QETSymbolPreview")
        self.preview.setMinimumSize(0, 250)
        self.preview.setFrameShape(QFrame.Shape.NoFrame)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.preview.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        self.preview_heading = QLabel("SOURCE VECTOR")
        self.preview_heading.setObjectName("SectionEyebrow")
        self.preview_badge = QLabel("CANDIDATE · NOT APPROVED FOR SLD")
        self.preview_badge.setObjectName("CandidateStatus")
        self.preview_badge.setToolTip(
            "Source-library artwork only. It is not approved as a power-system one-line symbol."
        )

        self.details = QLabel(
            "Acquire the pinned QElectroTech symbol seed to browse source assets."
        )
        self.details.setObjectName("QETProvenanceDetails")
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details.setMaximumHeight(145)
        self.details.setVisible(False)

        self.provenance_toggle = QToolButton()
        self.provenance_toggle.setObjectName("ProvenanceToggle")
        self.provenance_toggle.setText("Source provenance and terminal metadata")
        self.provenance_toggle.setCheckable(True)
        self.provenance_toggle.setChecked(False)
        self.provenance_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.provenance_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.provenance_toggle.toggled.connect(self._toggle_provenance)

        self.status = QLabel()
        self.status.setObjectName("QETLibraryStatus")
        self.status.setWordWrap(False)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status.setMaximumHeight(22)
        self.status.setToolTip("Pinned source repository, commit and licence information")

        self.rotate_left_button = QPushButton("−90°")
        self.rotate_left_button.setIcon(
            engineering_icon(self.style(), "fa5s.undo-alt", QStyle.StandardPixmap.SP_ArrowBack)
        )
        self.rotate_left_button.setToolTip("Rotate preview 90 degrees counterclockwise")
        self.rotate_right_button = QPushButton("+90°")
        self.rotate_right_button.setIcon(
            engineering_icon(self.style(), "fa5s.redo-alt", QStyle.StandardPixmap.SP_ArrowForward)
        )
        self.rotate_right_button.setToolTip("Rotate preview 90 degrees clockwise")
        self.rotate_left_button.setEnabled(False)
        self.rotate_right_button.setEnabled(False)
        self.rotate_left_button.clicked.connect(lambda: self._rotate_preview(-90.0))
        self.rotate_right_button.clicked.connect(lambda: self._rotate_preview(90.0))

        self.insert_button = QPushButton("Place drawing ref")
        self.insert_button.setObjectName("PrimaryAction")
        self.insert_button.setIcon(
            engineering_icon(
                self.style(), "fa5s.plus", QStyle.StandardPixmap.SP_FileDialogNewFolder
            )
        )
        self.insert_button.setToolTip(
            "Places this source vector as an unconnected drawing candidate. "
            "It is not an approved single-line symbol or electrical equipment."
        )
        self.insert_button.setEnabled(False)
        self.insert_button.clicked.connect(self._request_insert)

        self.refresh_button = QPushButton()
        self.refresh_button.setIcon(
            engineering_icon(self.style(), "fa5s.sync-alt", QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.refresh_button.setFixedWidth(38)
        self.refresh_button.setToolTip("Reload the pinned QElectroTech source catalog")
        self.refresh_button.clicked.connect(self.refresh_library)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 5, 0)
        left_layout.setSpacing(7)
        source_heading = QLabel("PINNED SOURCE ASSETS")
        source_heading.setObjectName("SectionEyebrow")
        left_layout.addWidget(source_heading)
        left_layout.addWidget(self.search)
        left_layout.addWidget(self.asset_list, 1)

        preview_frame = QFrame()
        preview_frame.setObjectName("SymbolPreviewFrame")
        preview_frame_layout = QVBoxLayout(preview_frame)
        preview_frame_layout.setContentsMargins(4, 4, 4, 4)
        preview_frame_layout.addWidget(self.preview)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(5, 0, 0, 0)
        right_layout.setSpacing(8)
        preview_meta = QHBoxLayout()
        preview_meta.addWidget(self.preview_heading)
        preview_meta.addStretch(1)
        preview_meta.addWidget(self.preview_badge)
        right_layout.addLayout(preview_meta)
        right_layout.addWidget(preview_frame, 1)

        self.library_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.library_splitter.setObjectName("QETLibrarySplitter")
        self.library_splitter.addWidget(left)
        self.library_splitter.addWidget(right)
        self.library_splitter.setHandleWidth(6)
        self.library_splitter.setChildrenCollapsible(True)
        self.library_splitter.setStretchFactor(0, 1)
        self.library_splitter.setStretchFactor(1, 3)
        self.library_splitter.setSizes([190, 500])

        controls = QHBoxLayout()
        controls.setSpacing(6)
        controls.addWidget(self.rotate_left_button)
        controls.addWidget(self.rotate_right_button)
        controls.addWidget(self.insert_button, 1)
        controls.addWidget(self.refresh_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(8)
        layout.addWidget(self.library_splitter, 1)
        layout.addWidget(self.provenance_toggle)
        layout.addWidget(self.details)
        layout.addWidget(self.status)
        layout.addLayout(controls)
        self.refresh_library()

    def _toggle_provenance(self, expanded: bool) -> None:
        self.details.setVisible(expanded)
        self.provenance_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    def refresh_library(self) -> None:
        self.asset_list.clear()
        self.preview_scene.clear()
        self._preview_item = None
        self._preview_rotation = 0.0
        self.rotate_left_button.setEnabled(False)
        self.rotate_right_button.setEnabled(False)
        self.insert_button.setEnabled(False)
        self._definitions_by_asset_id.clear()
        try:
            self.catalog = load_qet_symbol_catalog(self.manifest_path, self.asset_root)
        except (QETSymbolError, OSError, ValueError) as exc:
            self.catalog = None
            self.status.setText("Pinned source library unavailable")
            self.status.setToolTip(str(exc))
            self.details.setText(
                "Run scripts/Acquire-QElectroTechSymbolSeed.ps1 from the repository root.\n"
                f"{exc}\nNo fallback or hand-drawn symbol will be shown."
            )
            return

        for symbol in self.catalog.symbols:
            asset_id = symbol.provenance.asset_id or symbol.source_uuid
            self._definitions_by_asset_id[asset_id] = symbol
            item = QListWidgetItem(symbol.name_for("es"))
            item.setData(Qt.ItemDataRole.UserRole, asset_id)
            item.setToolTip(
                f"Asset ID: {asset_id}\n"
                f"Source UUID: {symbol.source_uuid}\n"
                "Source-library status: candidate; not approved as a power-system SLD glyph\n"
                f"Normative status: {symbol.provenance.normative_status}\n"
                f"Source: {symbol.provenance.source_path}"
            )
            self.asset_list.addItem(item)

        self.status.setText(
            f"{len(self.catalog.symbols)} source assets · "
            f"{self.catalog.source_commit[:9]} · CC BY 3.0"
        )
        if self.asset_list.count():
            self.asset_list.setCurrentRow(0)

    def _filter_symbols(self, value: str) -> None:
        needle = value.casefold().strip()
        for row in range(self.asset_list.count()):
            item = self.asset_list.item(row)
            item.setHidden(needle not in item.text().casefold())

    def _selection_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        self.insert_button.setEnabled(False)
        self.rotate_left_button.setEnabled(False)
        self.rotate_right_button.setEnabled(False)
        self._preview_item = None
        self._preview_rotation = 0.0
        self.preview_scene.clear()
        if current is None:
            return
        asset_id = current.data(Qt.ItemDataRole.UserRole)
        symbol = self._definitions_by_asset_id.get(asset_id)
        if symbol is None:
            return
        try:
            graphics_item = QETSymbolItem(symbol)
        except UnsupportedQETPrimitiveError as exc:
            self.details.setText(
                f"{symbol.name_for('es')}\nPreview unavailable: {exc}\n"
                "The source XML and primitives remain preserved; no substitute is drawn."
            )
            self.provenance_toggle.setChecked(True)
            self.symbol_selected.emit(asset_id)
            return

        self._preview_item = graphics_item
        self.preview_scene.addItem(graphics_item)
        self.insert_button.setEnabled(True)
        self.rotate_left_button.setEnabled(True)
        self.rotate_right_button.setEnabled(True)
        self._fit_preview()

        terminal_lines = [
            f"{terminal.name or '(unnamed)'} · {terminal.uuid[:8]} · "
            f"({terminal.position.x:g}, {terminal.position.y:g}) · {terminal.orientation}"
            for terminal in symbol.terminals
        ]
        terminal_summary = "\n".join(terminal_lines) or "No explicit terminals — preview only"
        self.details.setText(
            f"{symbol.name_for('es')}\n"
            f"Asset ID: {asset_id}\n"
            f"Source UUID: {symbol.source_uuid}\n"
            f"Source author: {symbol.author or 'Not stated'}\n"
            f"License: {symbol.provenance.license_identifier}\n"
            "Source-library status: candidate; not approved as a power-system single-line glyph\n"
            f"Normative status: {symbol.provenance.normative_status}\n"
            f"Git blob: {symbol.source_git_blob_sha1}\n"
            f"Terminals:\n{terminal_summary}"
        )
        self.provenance_toggle.setText(
            f"Source details · licence · {len(symbol.terminals)} terminal definitions"
        )
        self.provenance_toggle.setChecked(False)
        self.symbol_selected.emit(asset_id)

    def _rotate_preview(self, delta_deg: float) -> None:
        if self._preview_item is None:
            return
        self._preview_rotation = (self._preview_rotation + delta_deg) % 360.0
        self._preview_item.setRotation(self._preview_rotation)
        self._fit_preview()
        self.status.setText(
            f"Preview rotation: {self._preview_rotation:g}° · source geometry unchanged"
        )

    def selected_asset_id(self) -> str | None:
        item = self.asset_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def definition_for_asset(self, asset_id: str) -> SymbolDefinition:
        try:
            return self._definitions_by_asset_id[asset_id]
        except KeyError as exc:
            raise KeyError(f"The selected source asset is not loaded: {asset_id}") from exc

    def _request_insert(self) -> None:
        asset_id = self.selected_asset_id()
        if asset_id is not None and self.insert_button.isEnabled():
            self.insert_requested.emit(asset_id, self._preview_rotation)

    def _fit_preview(self) -> None:
        if self._preview_item is None:
            return
        self.preview.resetTransform()
        source_bounds = self._preview_item.sceneBoundingRect()
        margin = max(12.0, max(source_bounds.width(), source_bounds.height()) * 0.12)
        bounds = source_bounds.adjusted(-margin, -margin, margin, margin)
        self.preview_scene.setSceneRect(bounds)
        self.preview.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_preview)
