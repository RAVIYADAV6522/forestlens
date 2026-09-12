from src import detection
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
