from .clicks import CSS, VIDEO, ClickSpecError, normalize_clicks, video_size, viewport_size
from .flows import VIEWPORTS, simple_flow
from .manual import RecordingCancelled, record_manually
from .pick import pick_points
from .recorder import capture

__all__ = [
    "CSS",
    "VIDEO",
    "VIEWPORTS",
    "ClickSpecError",
    "RecordingCancelled",
    "capture",
    "normalize_clicks",
    "pick_points",
    "record_manually",
    "simple_flow",
    "video_size",
    "viewport_size",
]
