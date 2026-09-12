import numpy as np

from src import io_utils, metrics, pipeline
from src.detection import Detection
from src.io_utils import GSD_METADATA, GSD_USER


def source(**kwargs):
    return io_utils.from_array(np.zeros((50, 40, 3), dtype=np.uint8), name="scene.png", **kwargs)


def test_user_gsd_is_recorded_as_user_supplied():
    result = pipeline.apply_gsd(source(), 0.5)
    assert result.gsd == 0.5
    assert result.gsd_origin == GSD_USER
    assert result.ground_area_m2() == 50 * 40 * 0.25


def test_metadata_gsd_is_not_overwritten_by_the_user():
    original = source(gsd=0.31, gsd_origin=GSD_METADATA)
    result = pipeline.apply_gsd(original, 0.5)
    assert result.gsd == 0.31
    assert any("metadata was kept" in note for note in result.notes)


def test_blank_gsd_leaves_the_image_unscaled():
    result = pipeline.apply_gsd(source(), None)
    assert result.gsd is None
    assert result.ground_area_m2() is None


def test_csv_rows_leave_area_blank_without_gsd(tmp_path):
    crowns = metrics.build_crowns([Detection(id=1, box=(0, 0, 10, 10), score=0.8)])
    rows = io_utils.crowns_to_rows(crowns, gsd=None)
    assert rows[0]["area_m2"] == ""
    assert rows[0]["area_basis"] == metrics.AREA_FROM_BOX
    path = io_utils.write_csv(tmp_path / "crowns.csv", crowns, gsd=None)
    assert "bounding_box_proxy" in path.read_text()


def test_geojson_requires_georeferencing():
    crowns = metrics.build_crowns([Detection(id=1, box=(0, 0, 10, 10), score=0.8)])
    assert io_utils.crowns_to_geojson(source(), crowns) is None

    geo = source(crs="EPSG:32645", transform=(0.5, 0.0, 100.0, 0.0, -0.5, 900.0))
    payload = io_utils.crowns_to_geojson(geo, crowns)
    assert payload["features"][0]["geometry"]["coordinates"][0][0] == (100.0, 900.0)


def test_annotate_returns_an_image_of_the_same_size():
    crowns = metrics.build_crowns([Detection(id=1, box=(5, 5, 20, 20), score=0.8)])
    image = io_utils.annotate(source(), crowns)
    assert image.size == (40, 50)
