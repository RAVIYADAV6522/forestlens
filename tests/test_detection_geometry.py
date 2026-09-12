from src import detection, io_utils
from src.detection import Detection


def test_iou_of_identical_boxes_is_one():
    assert detection.iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0


def test_disjoint_boxes_have_zero_iou():
    assert detection.iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


def test_duplicate_suppression_keeps_highest_score():
    kept = detection.suppress_duplicates(
        [
            Detection(id=1, box=(0, 0, 10, 10), score=0.6),
            Detection(id=2, box=(1, 1, 11, 11), score=0.9),
            Detection(id=3, box=(50, 50, 60, 60), score=0.5),
        ],
        iou_threshold=0.4,
    )
    assert [d.score for d in kept] == [0.9, 0.5]


def test_edge_detections_are_flagged():
    inner = Detection(id=1, box=(40, 40, 60, 60), score=0.9)
    edge = Detection(id=2, box=(0, 10, 20, 30), score=0.9)
    detection.flag_edge_detections([inner, edge], width=100, height=100)
    assert inner.flags == []
    assert "clipped_at_image_edge" in edge.flags


def test_tiles_cover_the_whole_image():
    boxes = list(io_utils.tiles(width=1000, height=500, size=400, overlap=100))
    assert boxes
    assert max(x2 for _, _, x2, _ in boxes) == 1000
    assert max(y2 for _, _, _, y2 in boxes) == 500
    assert all(x2 - x1 <= 400 and y2 - y1 <= 400 for x1, y1, x2, y2 in boxes)
