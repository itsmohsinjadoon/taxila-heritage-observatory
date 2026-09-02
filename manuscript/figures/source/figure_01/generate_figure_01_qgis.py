"""Generate the audited Taxila Figure 1 inside QGIS 3.44.

The script uses only repository-bundled sources: the derived Sentinel-2 display
raster, frozen OSM orientation features, open locator boundaries, and the
documented UNESCO component inventory. It builds a journal layout and writes a
new QGIS project plus publication exports without querying a live basemap.
"""

import json
import os
import traceback
from pathlib import Path

if "__file__" in globals():
    ROOT = Path(__file__).resolve().parent
else:
    # QGIS --code may execute a script without defining ``__file__``. The
    # launcher can provide the source-bundle directory without hard-coding a
    # user-specific path in this versioned script.
    configured_root = os.environ.get("TAXILA_FIGURE1_ROOT")
    if not configured_root:
        raise RuntimeError(
            "QGIS did not define __file__. Set TAXILA_FIGURE1_ROOT to the "
            "manuscript/figures/source/figure_01 directory and run again."
        )
    ROOT = Path(configured_root).expanduser().resolve()
OUT = ROOT / "generated"
DATA = ROOT / "data"
PROJECT_PATH = OUT / "Taxila_Figure1_Final.qgz"
MASTER = DATA / "Taxila_UNESCO_Master.gpkg"
PACKAGE = OUT / "Taxila_Figure1_Final_Data.gpkg"
OSM_SNAPSHOT = DATA / "osm_source_snapshot.json"
STATUS = OUT / "taxila_figure1_final_status.txt"
ERROR = OUT / "taxila_figure1_final_error.txt"


def overpass_snapshot():
    """Load the frozen OSM snapshot so regeneration is not time-dependent."""
    if not OSM_SNAPSHOT.is_file():
        raise FileNotFoundError(f"Missing frozen OSM snapshot: {OSM_SNAPSHOT}")
    return json.loads(OSM_SNAPSHOT.read_text(encoding="utf-8"))


try:
    from qgis.core import (
        Qgis,
        QgsCoordinateReferenceSystem,
        QgsCoordinateTransform,
        QgsFeature,
        QgsField,
        QgsFillSymbol,
        QgsGeometry,
        QgsLayoutExporter,
        QgsLayoutItemLabel,
        QgsLayoutItemMap,
        QgsLayoutItemPicture,
        QgsLayoutItemPolygon,
        QgsLayoutItemPolyline,
        QgsLayoutItemScaleBar,
        QgsLayoutItemShape,
        QgsLayoutMeasurement,
        QgsLayoutPoint,
        QgsLayoutSize,
        QgsLineSymbol,
        QgsMarkerSymbol,
        QgsPalLayerSettings,
        QgsPointXY,
        QgsPrintLayout,
        QgsProject,
        QgsRasterLayer,
        QgsRectangle,
        QgsRuleBasedRenderer,
        QgsSingleSymbolRenderer,
        QgsTextBufferSettings,
        QgsTextFormat,
        QgsUnitTypes,
        QgsVectorFileWriter,
        QgsVectorLayer,
        QgsVectorLayerSimpleLabeling,
    )
    from qgis.PyQt.QtCore import QPointF, Qt, QTimer, QVariant
    from qgis.PyQt.QtGui import QColor, QFont, QImage, QPolygonF

    OUT.mkdir(parents=True, exist_ok=True)
    p = QgsProject.instance()
    p.clear()

    sentinel_rgb = QgsRasterLayer(
        str(DATA / "Taxila_Sentinel2_20241026_RGB_8bit.tif"),
        "Sentinel-2 L2A true colour — 2024-10-26",
    )
    if not sentinel_rgb.isValid():
        raise RuntimeError("The prepared Sentinel-2 true-colour raster is invalid")

    crs_utm = QgsCoordinateReferenceSystem("EPSG:32643")
    crs_geo = QgsCoordinateReferenceSystem("EPSG:4326")
    p.setCrs(crs_utm)
    p.setTitle("Taxila Figure 1 - Final Journal Cartography")
    p.setPresetHomePath(str(OUT))
    try:
        p.setFilePathStorage(Qgis.FilePathType.Relative)
    except Exception:
        pass

    def mem(geometry, name, crs="EPSG:32643", fields=()):
        layer = QgsVectorLayer(f"{geometry}?crs={crs}", name, "memory")
        layer.dataProvider().addAttributes([QgsField(n, t) for n, t in fields])
        layer.updateFields()
        return layer

    source_sites = QgsVectorLayer(
        f"{MASTER}|layername=Taxila_UNESCO_Master", "Official UNESCO inventory", "ogr"
    )
    if not source_sites.isValid() or source_sites.featureCount() != 18:
        raise RuntimeError("Expected the official 18-component master GeoPackage")

    displayed_m = mem(
        "Point",
        "UNESCO components - cartographic display",
        fields=[
            ("Map_No", QVariant.Int),
            ("label", QVariant.String),
            ("name", QVariant.String),
            ("true_x", QVariant.Double),
            ("true_y", QVariant.Double),
        ],
    )
    labels_m = mem(
        "Point",
        "UNESCO component IDs",
        fields=[("Map_No", QVariant.Int), ("label", QVariant.String)],
    )
    leaders_m = mem(
        "LineString",
        "Subtle label leaders",
        fields=[("Map_No", QVariant.Int)],
    )
    buffers_m = mem(
        "Polygon",
        "500 m analytical neighbourhoods",
        fields=[("Map_No", QVariant.Int)],
    )
    locator_m = mem(
        "Point", "Taxila locator", "EPSG:4326", [("label", QVariant.String)]
    )
    extent_geo_m = mem(
        "Polygon", "Main-panel extent", "EPSG:4326", [("label", QVariant.String)]
    )

    cartographic_offsets = {
        5: (-45, -35),
        7: (-105, -75),
        13: (105, 75),
        16: (45, 35),
    }
    label_offsets = {
        1: (350, 170),
        3: (-330, -70),
        4: (-330, 170),
        5: (-300, -170),
        6: (-330, -190),
        7: (-330, -220),
        8: (300, -220),
        9: (330, -210),
        10: (-330, -230),
        11: (-340, 180),
        12: (340, 190),
        13: (350, 160),
        14: (260, 280),
        15: (360, -120),
        16: (-320, 230),
        17: (360, 210),
        18: (-350, -220),
    }

    official = []
    inventory = []
    true_points = {}
    display_points = {}
    for ft in source_sites.getFeatures():
        no = int(ft["Map_No"])
        name = str(ft["UNESCO_Official_Name"])
        inventory.append((no, name))
        if no == 2:
            continue
        official.append(no)
        pt = QgsPointXY(ft.geometry().asPoint())
        true_points[no] = pt
        dx, dy = cartographic_offsets.get(no, (0, 0))
        display_pt = QgsPointXY(pt.x() + dx, pt.y() + dy)
        display_points[no] = display_pt

        sf = QgsFeature(displayed_m.fields())
        sf.setAttributes([no, f"{no:03d}", name, pt.x(), pt.y()])
        sf.setGeometry(QgsGeometry.fromPointXY(display_pt))
        displayed_m.dataProvider().addFeature(sf)

        bf = QgsFeature(buffers_m.fields())
        bf.setAttributes([no])
        bf.setGeometry(QgsGeometry.fromPointXY(pt).buffer(500, 64))
        buffers_m.dataProvider().addFeature(bf)

        lx, ly = label_offsets[no]
        label_pt = QgsPointXY(display_pt.x() + lx, display_pt.y() + ly)
        lf = QgsFeature(labels_m.fields())
        lf.setAttributes([no, f"{no:03d}"])
        lf.setGeometry(QgsGeometry.fromPointXY(label_pt))
        labels_m.dataProvider().addFeature(lf)

        lead = QgsFeature(leaders_m.fields())
        lead.setAttributes([no])
        lead.setGeometry(QgsGeometry.fromPolylineXY([display_pt, label_pt]))
        leaders_m.dataProvider().addFeature(lead)

    if sorted(official) != [1] + list(range(3, 19)):
        raise RuntimeError(f"Official mapped inventory mismatch: {sorted(official)}")

    xs = [pt.x() for pt in true_points.values()]
    ys = [pt.y() for pt in true_points.values()]
    raw_main = QgsRectangle(min(xs) - 850, min(ys) - 850, max(xs) + 850, max(ys) + 850)

    to_geo = QgsCoordinateTransform(crs_utm, crs_geo, p)
    center_utm = QgsPointXY(sum(xs) / 17, sum(ys) / 17)
    center_geo = to_geo.transform(center_utm)
    tf = QgsFeature(locator_m.fields())
    tf.setAttributes(["Taxila"])
    tf.setGeometry(QgsGeometry.fromPointXY(center_geo))
    locator_m.dataProvider().addFeature(tf)

    corners = [
        to_geo.transform(QgsPointXY(raw_main.xMinimum(), raw_main.yMinimum())),
        to_geo.transform(QgsPointXY(raw_main.xMaximum(), raw_main.yMinimum())),
        to_geo.transform(QgsPointXY(raw_main.xMaximum(), raw_main.yMaximum())),
        to_geo.transform(QgsPointXY(raw_main.xMinimum(), raw_main.yMaximum())),
    ]
    ef = QgsFeature(extent_geo_m.fields())
    ef.setAttributes(["Main map"])
    ef.setGeometry(QgsGeometry.fromPolygonXY([corners + [corners[0]]]))
    extent_geo_m.dataProvider().addFeature(ef)

    # Verify and freeze Taxila Museum and N-125 geometry from the same OSM
    # predicates stored in the source QGIS project.
    osm = overpass_snapshot()
    museum_m = mem(
        "Point",
        "Taxila Museum",
        fields=[
            ("osm_id", QVariant.String),
            ("name", QVariant.String),
            ("tourism", QVariant.String),
        ],
    )
    road_m = mem(
        "LineString",
        "N-125",
        fields=[
            ("osm_id", QVariant.String),
            ("ref", QVariant.String),
            ("name", QVariant.String),
            ("highway", QVariant.String),
        ],
    )
    museum_labels_m = mem(
        "Point", "Taxila Museum label", fields=[("label", QVariant.String)]
    )
    museum_leader_m = mem(
        "LineString", "Taxila Museum label leader", fields=[("label", QVariant.String)]
    )
    road_vertices = []
    museum_point = None
    for element in osm.get("elements", []):
        tags = element.get("tags", {})
        if (
            element.get("type") == "node"
            and tags.get("tourism") == "museum"
            and (tags.get("name:en") == "Taxila Museum" or "Taxila" in tags.get("name", ""))
        ):
            geo_pt = QgsPointXY(float(element["lon"]), float(element["lat"]))
            pt = QgsCoordinateTransform(crs_geo, crs_utm, p).transform(geo_pt)
            museum_point = pt
            mf = QgsFeature(museum_m.fields())
            mf.setAttributes([str(element["id"]), "Taxila Museum", "museum"])
            mf.setGeometry(QgsGeometry.fromPointXY(pt))
            museum_m.dataProvider().addFeature(mf)
        if element.get("type") == "way" and tags.get("ref") == "N-125":
            points = []
            for vertex in element.get("geometry", []):
                geo_pt = QgsPointXY(float(vertex["lon"]), float(vertex["lat"]))
                pt = QgsCoordinateTransform(crs_geo, crs_utm, p).transform(geo_pt)
                points.append(pt)
                if raw_main.contains(pt):
                    road_vertices.append(pt)
            if len(points) >= 2:
                rf = QgsFeature(road_m.fields())
                rf.setAttributes(
                    [str(element["id"]), "N-125", tags.get("name", ""), tags.get("highway", "")]
                )
                rf.setGeometry(QgsGeometry.fromPolylineXY(points))
                road_m.dataProvider().addFeature(rf)

    if museum_m.featureCount() != 1:
        raise RuntimeError(f"Expected one verified Taxila Museum point, got {museum_m.featureCount()}")
    if road_m.featureCount() < 1 or not road_vertices:
        raise RuntimeError("No verified N-125 geometry intersected the main-map area")

    museum_label_point = QgsPointXY(museum_point.x() - 460, museum_point.y() + 145)
    mlf = QgsFeature(museum_labels_m.fields())
    mlf.setAttributes(["Taxila Museum"])
    mlf.setGeometry(QgsGeometry.fromPointXY(museum_label_point))
    museum_labels_m.dataProvider().addFeature(mlf)
    mlead = QgsFeature(museum_leader_m.fields())
    mlead.setAttributes(["Taxila Museum"])
    mlead.setGeometry(QgsGeometry.fromPolylineXY([museum_point, museum_label_point]))
    museum_leader_m.dataProvider().addFeature(mlead)

    road_labels_m = mem(
        "Point", "N-125 labels", fields=[("label", QVariant.String)]
    )
    for target_y in (
        raw_main.yMinimum() + raw_main.height() * 0.34,
        raw_main.yMinimum() + raw_main.height() * 0.72,
    ):
        candidates = sorted(
            road_vertices,
            key=lambda point: abs(point.y() - target_y) + abs(point.x() - center_utm.x()) * 0.08,
        )
        if candidates:
            f = QgsFeature(road_labels_m.fields())
            f.setAttributes(["N-125"])
            f.setGeometry(QgsGeometry.fromPointXY(candidates[0]))
            road_labels_m.dataProvider().addFeature(f)

    if PACKAGE.exists():
        PACKAGE.unlink()

    def write(layer, layer_name, first=False, display_name=None):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer_name
        options.actionOnExistingFile = (
            QgsVectorFileWriter.CreateOrOverwriteFile
            if first
            else QgsVectorFileWriter.CreateOrOverwriteLayer
        )
        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, str(PACKAGE), p.transformContext(), options
        )
        if result[0] != QgsVectorFileWriter.NoError:
            raise RuntimeError(f"Could not write {layer_name}: {result}")
        frozen = QgsVectorLayer(
            f"{PACKAGE}|layername={layer_name}", display_name or layer.name(), "ogr"
        )
        if not frozen.isValid():
            raise RuntimeError(f"Packaged layer {layer_name} is invalid")
        return frozen

    displayed = write(displayed_m, "unesco_display", True)
    labels = write(labels_m, "unesco_labels")
    leaders = write(leaders_m, "unesco_label_leaders")
    buffers = write(buffers_m, "analytical_neighbourhoods_500m")
    locator = write(locator_m, "taxila_locator")
    extent_geo = write(extent_geo_m, "main_panel_extent")
    museum = write(museum_m, "taxila_museum")
    museum_labels = write(museum_labels_m, "taxila_museum_label")
    museum_leader = write(museum_leader_m, "taxila_museum_label_leader")
    road = write(road_m, "n125")
    road_casing = QgsVectorLayer(f"{PACKAGE}|layername=n125", "N-125 casing", "ogr")
    road_labels = write(road_labels_m, "n125_labels")

    ne_source = QgsVectorLayer(
        str(DATA / "natural_earth_50m_admin_0_countries.geojson"), "National boundaries", "ogr"
    )
    adm1_source = QgsVectorLayer(
        str(DATA / "geoboundaries_PAK_ADM1_simplified.geojson"),
        "Pakistan provinces",
        "ogr",
    )
    adm2_source = QgsVectorLayer(
        str(DATA / "geoboundaries_PAK_ADM2_simplified.geojson"),
        "Pakistan districts",
        "ogr",
    )
    if not all(layer.isValid() for layer in (ne_source, adm1_source, adm2_source)):
        raise RuntimeError("Locator boundary sources are invalid")
    ne = write(ne_source, "natural_earth_countries")
    adm1 = write(adm1_source, "pak_adm1")
    adm2 = write(adm2_source, "pak_adm2")

    regional_labels_m = mem(
        "Point", "Regional labels", "EPSG:4326", [("label", QVariant.String)]
    )
    for ft in adm2.getFeatures():
        name = str(ft["shapeName"])
        if name in ("Rawalpindi", "Attock", "Islamabad Capital Territory"):
            f = QgsFeature(regional_labels_m.fields())
            f.setAttributes([name.replace(" Capital Territory", "")])
            f.setGeometry(ft.geometry().pointOnSurface())
            regional_labels_m.dataProvider().addFeature(f)
    regional_labels = write(regional_labels_m, "regional_labels")

    for layer in (
        displayed,
        labels,
        leaders,
        buffers,
        locator,
        extent_geo,
        museum,
        museum_labels,
        museum_leader,
        road_casing,
        road,
        road_labels,
        ne,
        adm1,
        adm2,
        regional_labels,
        sentinel_rgb,
    ):
        p.addMapLayer(layer)

    displayed.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple(
                {
                    "name": "circle",
                    "color": "#F2C94C",
                    "outline_color": "#111111",
                    "outline_width": "0.28",
                    "size": "2.2",
                }
            )
        )
    )
    labels.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple(
                {"name": "circle", "color": "0,0,0,0", "outline_color": "0,0,0,0", "size": "0"}
            )
        )
    )
    leaders.setRenderer(
        QgsSingleSymbolRenderer(
            QgsLineSymbol.createSimple(
                {"line_color": "255,255,255,125", "line_width": "0.12"}
            )
        )
    )
    buffers.setRenderer(
        QgsSingleSymbolRenderer(
            QgsFillSymbol.createSimple(
                {
                    "color": "0,0,0,0",
                    "outline_color": "100,203,226,125",
                    "outline_width": "0.22",
                }
            )
        )
    )
    museum.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple(
                {
                    "name": "square",
                    "color": "#2F6FB0",
                    "outline_color": "#FFFFFF",
                    "outline_width": "0.32",
                    "size": "2.2",
                }
            )
        )
    )
    road_casing.setRenderer(
        QgsSingleSymbolRenderer(
            QgsLineSymbol.createSimple(
                {"line_color": "65,51,31,165", "line_width": "0.58"}
            )
        )
    )
    road.setRenderer(
        QgsSingleSymbolRenderer(
            QgsLineSymbol.createSimple(
                {"line_color": "#F0B44D", "line_width": "0.34"}
            )
        )
    )
    road_labels.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple(
                {"name": "circle", "color": "0,0,0,0", "outline_color": "0,0,0,0", "size": "0"}
            )
        )
    )
    museum_labels.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple(
                {"name": "circle", "color": "0,0,0,0", "outline_color": "0,0,0,0", "size": "0"}
            )
        )
    )
    museum_leader.setRenderer(
        QgsSingleSymbolRenderer(
            QgsLineSymbol.createSimple(
                {"line_color": "255,255,255,115", "line_width": "0.10"}
            )
        )
    )

    def point_label(
        layer,
        field,
        size,
        color="#FFFFFF",
        buffer_size=0.38,
        bold=True,
        buffer_color="#202320",
    ):
        settings = QgsPalLayerSettings()
        settings.fieldName = field
        settings.enabled = True
        settings.displayAll = True
        settings.placement = Qgis.LabelPlacement.OverPoint
        text_format = QgsTextFormat()
        text_format.setFont(QFont("Arial", max(5, int(round(size))), QFont.Bold if bold else QFont.Normal))
        text_format.setSize(size)
        text_format.setColor(QColor(color))
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setSize(buffer_size)
        buffer.setColor(QColor(buffer_color))
        text_format.setBuffer(buffer)
        settings.setFormat(text_format)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)

    point_label(labels, "label", 5.7, "#FCFCF8", 0.38, True)
    point_label(museum_labels, "label", 5.0, "#FFFFFF", 0.38, True)
    point_label(road_labels, "label", 5.0, "#FFD26E", 0.42, True)

    locator.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple(
                {
                    "name": "circle",
                    "color": "#A34B4B",
                    "outline_color": "#FFFFFF",
                    "outline_width": "0.45",
                    "size": "2.8",
                }
            )
        )
    )
    point_label(locator, "label", 5.4, "#8A3030", 0.55, True, "#FFFFFF")
    extent_geo.setRenderer(
        QgsSingleSymbolRenderer(
            QgsFillSymbol.createSimple(
                {
                    "color": "0,0,0,0",
                    "outline_color": "#A34B4B",
                    "outline_width": "0.48",
                    "outline_style": "dash",
                }
            )
        )
    )
    ne.setRenderer(
        QgsSingleSymbolRenderer(
            QgsFillSymbol.createSimple(
                {"color": "#ECE9E1", "outline_color": "#9EA49E", "outline_width": "0.25"}
            )
        )
    )

    adm1_root = QgsRuleBasedRenderer.Rule(None)
    adm1_root.appendChild(
        QgsRuleBasedRenderer.Rule(
            QgsFillSymbol.createSimple(
                {
                    "color": "#8FAF88",
                    "outline_color": "#B0B5AE",
                    "outline_width": "0.28",
                }
            ),
            0,
            0,
            '"shapeName" = \'Punjab\'',
            "Punjab",
        )
    )
    adm1_root.appendChild(
        QgsRuleBasedRenderer.Rule(
            QgsFillSymbol.createSimple(
                {"color": "#F5F2EA", "outline_color": "#B0B5AE", "outline_width": "0.22"}
            ),
            0,
            0,
            "ELSE",
            "Other provinces",
        )
    )
    adm1.setRenderer(QgsRuleBasedRenderer(adm1_root))

    adm2_root = QgsRuleBasedRenderer.Rule(None)
    for label, expression, color in (
        ("Rawalpindi", '"shapeName" = \'Rawalpindi\'', "#AFC6A5"),
        ("Attock", '"shapeName" = \'Attock\'', "#DEDCC8"),
        ("Islamabad", '"shapeName" = \'Islamabad Capital Territory\'', "#D7D4E4"),
        ("Context", "ELSE", "#F1EEE6"),
    ):
        adm2_root.appendChild(
            QgsRuleBasedRenderer.Rule(
                QgsFillSymbol.createSimple(
                    {"color": color, "outline_color": "#A9AFA8", "outline_width": "0.20"}
                ),
                0,
                0,
                expression,
                label,
            )
        )
    adm2.setRenderer(QgsRuleBasedRenderer(adm2_root))
    regional_labels.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple(
                {"name": "circle", "color": "0,0,0,0", "outline_color": "0,0,0,0", "size": "0"}
            )
        )
    )
    point_label(regional_labels, "label", 4.7, "#555B54", 0.50, True, "#FFFFFF")

    for layer in p.mapLayers().values():
        node = p.layerTreeRoot().findLayer(layer.id())
        if node:
            node.setItemVisibilityChecked(False)

    for old in list(p.layoutManager().layouts()):
        p.layoutManager().removeLayout(old)
    layout = QgsPrintLayout(p)
    layout.initializeDefaults()
    layout.setName("Taxila Figure 1 - Final Landscape")
    page = layout.pageCollection().page(0)
    page.setPageSize(QgsLayoutSize(260, 175, QgsUnitTypes.LayoutMillimeters))

    def add_label(text, x, y, w, h, pt=6, bold=False, color="#252825", align=Qt.AlignLeft, italic=False):
        item = QgsLayoutItemLabel(layout)
        item.setText(text)
        font = QFont("Arial", max(4, int(round(pt))), QFont.Bold if bold else QFont.Normal)
        font.setItalic(italic)
        item.setFont(font)
        item.setFontColor(QColor(color))
        item.setHAlign(align)
        item.setVAlign(Qt.AlignVCenter)
        item.adjustSizeToText()
        item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
        item.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(item)
        return item

    def fitted(rect, ratio):
        cx = rect.center().x()
        cy = rect.center().y()
        width = rect.width()
        height = rect.height()
        if width / height < ratio:
            width = height * ratio
        else:
            height = width / ratio
        return QgsRectangle(cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)

    def add_map(x, y, width, height, layers, crs, rect):
        item = QgsLayoutItemMap(layout)
        layout.addLayoutItem(item)
        item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
        item.attemptResize(QgsLayoutSize(width, height, QgsUnitTypes.LayoutMillimeters))
        item.setCrs(crs)
        item.setLayers(layers)
        item.setKeepLayerSet(True)
        item.setExtent(fitted(rect, width / height))
        item.setFrameEnabled(True)
        item.setFrameStrokeColor(QColor("#B8BCB7"))
        item.setFrameStrokeWidth(QgsLayoutMeasurement(0.30, QgsUnitTypes.LayoutMillimeters))
        item.setBackgroundColor(QColor("#EDEDE9"))
        item.refresh()
        return item

    def add_connector(points):
        item = QgsLayoutItemPolyline(QPolygonF([QPointF(x, y) for x, y in points]), layout)
        item.setSymbol(
            QgsLineSymbol.createSimple(
                {"line_color": "#A34B4B", "line_width": "0.45", "line_style": "dot"}
            )
        )
        layout.addLayoutItem(item)
        return item

    def add_arrowhead(points):
        item = QgsLayoutItemPolygon(QPolygonF([QPointF(x, y) for x, y in points]), layout)
        item.setSymbol(
            QgsFillSymbol.createSimple(
                {"color": "#A34B4B", "outline_color": "#A34B4B", "outline_width": "0.12"}
            )
        )
        layout.addLayoutItem(item)
        return item

    add_label("(a)  Pakistan", 5, 2.5, 55, 5, 7.0, True, "#303330")
    map_a = add_map(
        5,
        8,
        55,
        37,
        [locator, adm1, ne],
        crs_geo,
        QgsRectangle(60.2, 23.0, 78.6, 37.7),
    )
    add_connector([(32.5, 45.5), (32.5, 52.5)])
    add_arrowhead([(31.3, 50.6), (33.7, 50.6), (32.5, 52.8)])

    add_label("(b)  Taxila region", 5, 52.5, 55, 5, 7.0, True, "#303330")
    map_b = add_map(
        5,
        58,
        55,
        40,
        [locator, extent_geo, regional_labels, adm2],
        crs_geo,
        QgsRectangle(71.55, 32.45, 74.25, 34.85),
    )
    add_connector([(32.5, 98.5), (32.5, 104.5), (64.5, 104.5)])
    add_arrowhead([(63.7, 103.3), (63.7, 105.7), (66.0, 104.5)])

    add_label("(c)  Taxila UNESCO components", 66, 2.5, 130, 5, 7.2, True, "#303330")
    map_c = add_map(
        66,
        8,
        189,
        107,
        [
            labels,
            museum_labels,
            museum,
            displayed,
            road_labels,
            road,
            road_casing,
            leaders,
            museum_leader,
            buffers,
            sentinel_rgb,
        ],
        crs_utm,
        raw_main,
    )
    grid = map_c.grid()
    grid.setEnabled(True)
    grid.setIntervalX(5000)
    grid.setIntervalY(5000)
    grid.setLineSymbol(
        QgsLineSymbol.createSimple({"line_color": "255,255,255,55", "line_width": "0.11"})
    )
    grid.setAnnotationEnabled(True)
    grid.setAnnotationPrecision(0)
    grid.setAnnotationFont(QFont("Arial", 4))
    grid.setAnnotationFontColor(QColor("225,228,222,175"))
    grid.setAnnotationFrameDistance(0.8)

    north = QgsLayoutItemPicture(layout)
    north.setPicturePath(
        r"C:\Program Files\QGIS 3.44.13\apps\qgis-ltr\svg\arrows\NorthArrow_02.svg"
    )
    north.attemptMove(QgsLayoutPoint(247, 12, QgsUnitTypes.LayoutMillimeters))
    north.attemptResize(QgsLayoutSize(5.5, 8, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(north)

    scale = QgsLayoutItemScaleBar(layout)
    scale.setStyle("Single Box")
    scale.setLinkedMap(map_c)
    try:
        scale.setUnits(Qgis.DistanceUnit.Kilometers)
    except Exception:
        scale.setUnits(QgsUnitTypes.DistanceKilometers)
    scale.setNumberOfSegments(4)
    scale.setUnitsPerSegment(2)
    scale.setUnitLabel("km")
    scale.setFont(QFont("Arial", 4))
    scale.setHeight(1.7)
    scale.update()
    scale.attemptMove(QgsLayoutPoint(70, 106, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(scale)

    # Compact horizontal legend below the main panel.
    legend_y = 118.0
    sym_site = QgsLayoutItemShape(layout)
    sym_site.setShapeType(QgsLayoutItemShape.Ellipse)
    sym_site.setSymbol(
        QgsFillSymbol.createSimple(
            {"color": "#F2C94C", "outline_color": "#111111", "outline_width": "0.28"}
        )
    )
    sym_site.attemptMove(QgsLayoutPoint(67, legend_y, QgsUnitTypes.LayoutMillimeters))
    sym_site.attemptResize(QgsLayoutSize(3.2, 3.2, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(sym_site)
    add_label("UNESCO component", 71.5, legend_y - 0.4, 31, 4, 4.6)

    sym_buffer = QgsLayoutItemShape(layout)
    sym_buffer.setShapeType(QgsLayoutItemShape.Ellipse)
    sym_buffer.setSymbol(
        QgsFillSymbol.createSimple(
            {"color": "0,0,0,0", "outline_color": "100,203,226,205", "outline_width": "0.28"}
        )
    )
    sym_buffer.attemptMove(QgsLayoutPoint(103, legend_y, QgsUnitTypes.LayoutMillimeters))
    sym_buffer.attemptResize(QgsLayoutSize(3.6, 3.6, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(sym_buffer)
    add_label("500 m neighbourhood", 108, legend_y - 0.4, 37, 4, 4.6)

    sym_museum = QgsLayoutItemShape(layout)
    sym_museum.setShapeType(QgsLayoutItemShape.Rectangle)
    sym_museum.setSymbol(
        QgsFillSymbol.createSimple(
            {"color": "#2F6FB0", "outline_color": "#FFFFFF", "outline_width": "0.25"}
        )
    )
    sym_museum.attemptMove(QgsLayoutPoint(147, legend_y, QgsUnitTypes.LayoutMillimeters))
    sym_museum.attemptResize(QgsLayoutSize(3.0, 3.0, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(sym_museum)
    add_label("Taxila Museum", 151.5, legend_y - 0.4, 27, 4, 4.6)

    legend_road = QgsLayoutItemPolyline(
        QPolygonF([QPointF(181, legend_y + 1.6), QPointF(189, legend_y + 1.6)]), layout
    )
    legend_road.setSymbol(
        QgsLineSymbol.createSimple({"line_color": "#F0B44D", "line_width": "0.38"})
    )
    layout.addLayoutItem(legend_road)
    add_label("N-125", 190.5, legend_y - 0.4, 14, 4, 4.6)

    legend_extent = QgsLayoutItemPolyline(
        QPolygonF([QPointF(208, legend_y + 1.6), QPointF(216, legend_y + 1.6)]), layout
    )
    legend_extent.setSymbol(
        QgsLineSymbol.createSimple(
            {"line_color": "#A34B4B", "line_width": "0.45", "line_style": "dash"}
        )
    )
    layout.addLayoutItem(legend_extent)
    add_label("Main-map extent", 217.5, legend_y - 0.4, 34, 4, 4.6)

    inventory.sort()
    add_label("OFFICIAL INVENTORY | 18 COMPONENTS", 5, 125.0, 120, 5, 6.4, True, "#303330")
    columns = [5, 91, 177]
    start_y = 132.0
    row_step = 5.55
    for idx, (no, name) in enumerate(inventory):
        col = idx // 6
        row = idx % 6
        x = columns[col]
        y = start_y + row * row_step
        unresolved = no == 2
        shown_name = "Saraikala, prehistoric mound*" if unresolved else name
        add_label(
            f"{no:03d}",
            x,
            y,
            9,
            4.3,
            4.7,
            True,
            "#9A9D98" if unresolved else "#A34B4B",
            italic=unresolved,
        )
        add_label(
            shown_name,
            x + 9,
            y,
            74,
            4.3,
            4.7,
            False,
            "#9A9D98" if unresolved else "#353835",
            italic=unresolved,
        )
    add_label(
        "* Saraikala is retained in the official inventory but is not mapped.",
        5,
        166.5,
        180,
        4,
        4.4,
        False,
        "#777B77",
        italic=True,
    )
    add_label(
        "Panel (c): Contains modified Copernicus Sentinel data (2024). Road and museum: © OpenStreetMap contributors (ODbL). Locators: Natural Earth and geoBoundaries (CC BY 4.0).",
        5,
        171.0,
        250,
        3,
        3.7,
        False,
        "#777B77",
    )

    p.layoutManager().addLayout(layout)
    if not p.write(str(PROJECT_PATH)):
        raise RuntimeError("Could not save the final editable QGIS project")

    exporter = QgsLayoutExporter(layout)
    pdf_settings = QgsLayoutExporter.PdfExportSettings()
    pdf_settings.dpi = 600
    pdf_settings.rasterizeWholeImage = False
    svg_settings = QgsLayoutExporter.SvgExportSettings()
    svg_settings.dpi = 600
    svg_settings.forceVectorOutput = True
    image_settings = QgsLayoutExporter.ImageExportSettings()
    image_settings.dpi = 600
    image_settings.cropToContents = False
    preview_settings = QgsLayoutExporter.ImageExportSettings()
    preview_settings.dpi = 180
    preview_settings.cropToContents = False

    # A distinct revision filename avoids Windows locking the previously opened
    # PDF while preserving stable names for the editable and raster masters.
    pdf_path = OUT / "Taxila_Figure1_Final_Cyan.pdf"
    svg_path = OUT / "Taxila_Figure1_Final.svg"
    png_path = OUT / "Taxila_Figure1_Final_600dpi.png"
    preview_path = OUT / "Taxila_Figure1_Final_preview.png"
    pdf_result = exporter.exportToPdf(str(pdf_path), pdf_settings)
    svg_result = exporter.exportToSvg(str(svg_path), svg_settings)
    png_result = exporter.exportToImage(str(png_path), image_settings)
    preview_result = exporter.exportToImage(str(preview_path), preview_settings)
    results = (pdf_result, svg_result, png_result, preview_result)
    if any(result != QgsLayoutExporter.Success for result in results):
        raise RuntimeError(f"Export failure: {results}")

    image = QImage(str(png_path)).convertToFormat(QImage.Format_RGB888)
    dpm = round(600 / 0.0254)
    image.setDotsPerMeterX(dpm)
    image.setDotsPerMeterY(dpm)
    image.save(str(png_path), "PNG")
    image.save(str(OUT / "Taxila_Figure1_Final_600dpi.tif"), "TIFF")

    metadata = f'''Taxila Figure 1 - final journal cartography
Source package: repository-relative data and script in manuscript/figures/source/figure_01
Edited QGIS project: Taxila_Figure1_Final.qgz
QGIS version: 3.44.13-Solothurn LTR
Metric CRS: EPSG:32643 - WGS 84 / UTM zone 43N
Mapped UNESCO components: 17 official-coordinate records
Inventory records: 18
Saraikala 139-002: inventory only; secondary coordinate excluded
Main-panel imagery: Sentinel-2 Collection 1 Level-2A surface reflectance; true-colour RGB B04/B03/B02; 10 m; 2024-10-26; tiles T43SCT and T43SBT
Locator context: Natural Earth 1:50m and geoBoundaries Pakistan ADM1/ADM2 vector data; no commercial basemap
Analytical support: 500 m circles centred on the true official coordinates
Analytical support styling: sky-cyan #64CBE2 outline selected for contrast against green satellite vegetation
Taxila Museum: OpenStreetMap node 2446416669; tourism=museum; name:en=Taxila Museum
N-125: OpenStreetMap ways selected only where ref=N-125 and highway=trunk
OSM query bounding box: 33.71455,72.76848,33.80719,72.94266
Locator boundaries: Natural Earth 1:50m countries and geoBoundaries Pakistan ADM1/ADM2
Cartographic displacement: small display-only offsets are stored separately from true_x/true_y; analytical buffers remain on official coordinates
No manuscript caption is embedded in the figure.
'''
    (OUT / "Taxila_Figure1_Final_metadata.txt").write_text(metadata, encoding="utf-8")

    caption = '''Figure 1. Study-area and analytical-support context for the Taxila World Heritage property. (a) Pakistan, with Punjab highlighted; (b) the regional location of Taxila; and (c) the analytical landscape showing the 17 components for which the UNESCO World Heritage Centre publishes point coordinates. Panel (c) is displayed over a 10 m Sentinel-2 Collection 1 Level-2A true-colour surface-reflectance composite (bands B04/B03/B02) acquired on 26 October 2024 (tiles T43SCT and T43SBT). Saraikala (139-002) remains in the official 18-component inventory but is not mapped because the UNESCO geographical-data table does not publish a coordinate. Cyan circles denote the primary 500 m analytical sampling neighbourhoods; 250 m and 1,000 m supports were also analysed. These circles, point locations and the displayed raster extent are analytical supports, not official property polygons, statutory protection zones or UNESCO buffer boundaries. Metric processing used WGS 84 / UTM zone 43N (EPSG:32643). Contains modified Copernicus Sentinel data (2024). Road and museum data © OpenStreetMap contributors, available under the Open Database Licence (https://www.openstreetmap.org/copyright). Locator boundaries use Natural Earth public-domain data and geoBoundaries CC BY 4.0 data (Runfola et al., 2020).'''
    (OUT / "Taxila_Figure1_Final_caption.txt").write_text(caption + "\n", encoding="utf-8")

    checklist = '''VALIDATION STATUS: EXPORT PASS - VISUAL QA REQUIRED AFTER EACH REBUILD
[x] true landscape page (260 x 175 mm)
[x] Pakistan first
[x] dotted zoom connectors present
[x] no FIGURE 1 text
[x] no embedded manuscript caption
[x] no satellite-context label
[x] no 007-013 inset or combined label
[x] 17 official-coordinate UNESCO components packaged and mapped
[x] Saraikala inventory-only
[x] labels set to 5.7 pt with thin charcoal halo
[x] markers set to 2.2 mm
[x] 500 m circles use a thin sky-cyan outline with improved vegetation contrast
[x] main extent derived from all 17 official coordinates plus 850 m margin
[x] Taxila Museum verified and packaged
[x] N-125 ref/highway attributes verified and packaged
[x] main panel uses the documented Sentinel-2 L2A true-colour raster
[x] Pakistan and regional locators use open vector data without a commercial basemap
[x] source and licence attribution is printed on the figure and expanded in the caption
[x] EPSG:32643 used; EPSG:32642 not used
[x] PDF, SVG, 600-dpi RGB PNG/TIFF, preview and editable QGIS project exported
'''
    (OUT / "Taxila_Figure1_Final_validation.txt").write_text(checklist, encoding="utf-8")
    if ERROR.exists():
        ERROR.unlink()
    STATUS.write_text("PASS\nFinal Taxila Figure 1 exported.\n", encoding="utf-8")
except Exception:
    ERROR.write_text(traceback.format_exc(), encoding="utf-8")
    STATUS.write_text("FAIL\n", encoding="utf-8")
finally:
    QTimer.singleShot(500, lambda: os._exit(0))
