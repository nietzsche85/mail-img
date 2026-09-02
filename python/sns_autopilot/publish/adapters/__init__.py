from .file import FileAdapter
from .instagram import InstagramAdapter
from .postiz import PostizAdapter
from .threads import ThreadsAdapter
from .webhook import WebhookAdapter
from .x import XAdapter
from .youtube import YouTubeAdapter

ADAPTERS = {
    "file": FileAdapter(),
    "webhook": WebhookAdapter(),
    "postiz": PostizAdapter(),
    "x": XAdapter(),
    "threads": ThreadsAdapter(),
    "instagram": InstagramAdapter(),
    "youtube": YouTubeAdapter(),
}

# 채널 하나만 담당하는 어댑터는 자기 플랫폼 글만 처리합니다.
OWNED_PLATFORM = {"x": "x", "threads": "threads", "instagram": "instagram", "youtube": "youtube"}

__all__ = ["ADAPTERS", "OWNED_PLATFORM"]
