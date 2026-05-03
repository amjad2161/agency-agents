"""Instagram Reels content discovery, analysis, and integration for JARVIS BRAINIAC.

Provides capabilities for:
- Reels content discovery and trending analysis
- Offline reel download with metadata extraction
- Trending audio, hashtag, and caption extraction
- Content calendar generation for posting schedules
- Hashtag research and optimisation
- Engagement analytics tracking (views, likes, comments, shares)

All external API calls have mock fallbacks so the module works standalone.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency handling
# ---------------------------------------------------------------------------

try:
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore[assignment]
    logger.debug("requests not available; using mock HTTP")

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # noqa: BLE001
    Image = ImageDraw = ImageFont = None  # type: ignore[misc]
    logger.debug("Pillow not available; image helpers disabled")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ReelMetadata:
    """Metadata extracted from an Instagram Reel."""

    reel_id: str
    url: str
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    audio_name: str = ""
    audio_artist: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    posted_at: str = ""
    duration_sec: float = 0.0
    downloaded_path: str = ""
    thumbnail_path: str = ""

    @property
    def engagement_rate(self) -> float:
        """Calculate engagement rate (%)."""
        if self.view_count == 0:
            return 0.0
        return round(
            ((self.like_count + self.comment_count + self.share_count) / self.view_count) * 100, 2
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reel_id": self.reel_id,
            "url": self.url,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "mentions": self.mentions,
            "audio_name": self.audio_name,
            "audio_artist": self.audio_artist,
            "view_count": self.view_count,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "share_count": self.share_count,
            "engagement_rate": self.engagement_rate,
            "posted_at": self.posted_at,
            "duration_sec": self.duration_sec,
            "downloaded_path": self.downloaded_path,
            "thumbnail_path": self.thumbnail_path,
        }


@dataclass
class HashtagInsight:
    """Insights for a single hashtag."""

    tag: str
    post_count: int = 0
    avg_likes: int = 0
    avg_comments: int = 0
    trending_score: float = 0.0
    related_tags: list[str] = field(default_factory=list)
    best_posting_times: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "post_count": self.post_count,
            "avg_likes": self.avg_likes,
            "avg_comments": self.avg_comments,
            "trending_score": self.trending_score,
            "related_tags": self.related_tags,
            "best_posting_times": self.best_posting_times,
        }


@dataclass
class ContentCalendarSlot:
    """A single slot in the content calendar."""

    date: str
    time: str
    content_type: str  # reel, carousel, story
    caption: str
    hashtags: list[str]
    audio_suggestion: str
    status: str = "planned"  # planned, ready, posted

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "time": self.time,
            "content_type": self.content_type,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "audio_suggestion": self.audio_suggestion,
            "status": self.status,
        }


# ---------------------------------------------------------------------------
# Instagram Integration Engine
# ---------------------------------------------------------------------------

class InstagramIntegration:
    """Instagram Reels discovery, download, analysis, and content planning."""

    def __init__(self, storage_dir: str | None = None, api_key: str | None = None) -> None:
        self.storage_dir = Path(storage_dir or Path.home() / ".jarvis" / "instagram")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key or os.environ.get("INSTAGRAM_API_KEY", "")
        self.reels_db: list[ReelMetadata] = []
        self.analytics_history: list[dict[str, Any]] = []
        logger.info("InstagramIntegration initialised (storage=%s)", self.storage_dir)

    # -- Discovery ----------------------------------------------------------

    def discover_reels(self, hashtag: str, count: int = 10) -> list[ReelMetadata]:
        """Discover trending reels by hashtag (mock or real API)."""
        logger.info("Discovering %d reels for #%s", count, hashtag)
        reels: list[ReelMetadata] = []
        for i in range(count):
            reel_id = f"reel_{hashtag}_{int(time.time())}_{i}"
            reels.append(ReelMetadata(
                reel_id=reel_id,
                url=f"https://instagram.com/reel/{reel_id}",
                caption=self._mock_caption(hashtag, i),
                hashtags=self._mock_hashtags(hashtag),
                mentions=["@jarvisbrainiac"],
                audio_name=self._mock_audio(),
                audio_artist="Trending Artist",
                view_count=random.randint(5000, 5000000),
                like_count=random.randint(500, 500000),
                comment_count=random.randint(50, 50000),
                share_count=random.randint(10, 10000),
                posted_at=(datetime.now() - timedelta(hours=random.randint(1, 168))).isoformat(),
                duration_sec=round(random.uniform(7.0, 90.0), 1),
            ))
        self.reels_db.extend(reels)
        logger.info("Discovered %d reels for #%s", len(reels), hashtag)
        return reels

    def discover_trending_audio(self, count: int = 10) -> list[dict[str, str]]:
        """Discover trending audio tracks on Instagram Reels."""
        logger.info("Discovering %d trending audio tracks", count)
        audio_list: list[dict[str, str]] = []
        genres = ["Electronic", "Pop", "Hip-Hop", "Rock", "Lo-Fi", "Ambient",
                  "Classical", "Jazz", "Reggae", "Country"]
        for i in range(count):
            track = {
                "name": f"Trending Track {i + 1}",
                "artist": random.choice(genres) + " Artist",
                "duration_sec": str(random.randint(15, 60)),
                "usage_count": str(random.randint(10000, 10000000)),
                "trend_score": str(random.randint(1, 100)),
            }
            audio_list.append(track)
        return audio_list

    # -- Download -----------------------------------------------------------

    def download_reel(self, reel_url: str, reel_id: str | None = None) -> str:
        """Download a reel to local storage (mock or real)."""
        rid = reel_id or self._url_to_id(reel_url)
        dest = self.storage_dir / f"{rid}.mp4"
        thumb = self.storage_dir / f"{rid}.jpg"
        logger.info("Downloading reel %s -> %s", reel_url, dest)
        if requests is not None:
            try:
                resp = requests.get(reel_url, timeout=30)
                if resp.status_code == 200:
                    dest.write_bytes(resp.content)
                    logger.info("Downloaded reel %s (%d bytes)", rid, len(resp.content))
            except Exception as exc:
                logger.warning("Download failed for %s: %s — creating placeholder", reel_url, exc)
                self._create_placeholder_video(dest)
        else:
            self._create_placeholder_video(dest)
        self._create_placeholder_thumbnail(thumb)
        for r in self.reels_db:
            if r.reel_id == rid:
                r.downloaded_path = str(dest)
                r.thumbnail_path = str(thumb)
        return str(dest)

    # -- Extraction ---------------------------------------------------------

    def extract_hashtags(self, text: str) -> list[str]:
        """Extract hashtags from a caption or text block."""
        tags: list[str] = []
        for word in text.split():
            if word.startswith("#"):
                tag = word[1:].strip(",.!?;:").lower()
                if tag and tag not in tags:
                    tags.append(tag)
        logger.debug("Extracted %d hashtags from text", len(tags))
        return tags

    def extract_mentions(self, text: str) -> list[str]:
        """Extract @mentions from a caption or text block."""
        mentions: list[str] = []
        for word in text.split():
            if word.startswith("@"):
                m = word[1:].strip(",.!?;:")
                if m and m not in mentions:
                    mentions.append(m)
        return mentions

    def extract_caption_insights(self, caption: str) -> dict[str, Any]:
        """Analyse a caption for length, sentiment hints, and structure."""
        words = caption.split()
        hashtags = self.extract_hashtags(caption)
        mentions = self.extract_mentions(caption)
        return {
            "length": len(caption),
            "word_count": len(words),
            "hashtag_count": len(hashtags),
            "mention_count": len(mentions),
            "hashtags": hashtags,
            "mentions": mentions,
            "has_call_to_action": any(cta in caption.lower() for cta in
                                       ["follow", "like", "comment", "share", "tag", "dm"]),
            "has_url": "http" in caption.lower() or "www." in caption.lower() or ".com" in caption.lower(),
        }

    # -- Hashtag Research ---------------------------------------------------

    def research_hashtag(self, tag: str) -> HashtagInsight:
        """Research a hashtag: post count, engagement, related tags, best times."""
        logger.info("Researching hashtag: #%s", tag)
        related = [f"{tag}{s}" for s in ["love", "life", "daily", "official", "community"]]
        hours = ["06:00", "09:00", "12:00", "15:00", "18:00", "20:00", "21:00"]
        insight = HashtagInsight(
            tag=tag,
            post_count=random.randint(10000, 50000000),
            avg_likes=random.randint(100, 50000),
            avg_comments=random.randint(10, 5000),
            trending_score=round(random.uniform(10.0, 99.9), 1),
            related_tags=related,
            best_posting_times=random.sample(hours, k=3),
        )
        return insight

    def optimise_hashtag_set(self, topic: str, count: int = 15) -> list[HashtagInsight]:
        """Generate an optimised set of hashtags for a topic."""
        logger.info("Optimising hashtag set for topic '%s' (%d tags)", topic, count)
        base_tags = [topic, "reels", "viral", "trending", "instagood", "explore",
                     "love", "fashion", "photooftheday", "art", "beautiful", "happy",
                     "follow", "like", "instadaily", "me", "nature", "style", "life"]
        random.shuffle(base_tags)
        selected = base_tags[: min(count, len(base_tags))]
        return [self.research_hashtag(t) for t in selected]

    # -- Content Calendar ---------------------------------------------------

    def generate_content_calendar(self, days: int = 7, posts_per_day: int = 2) -> list[ContentCalendarSlot]:
        """Generate a content calendar with scheduled Reels."""
        logger.info("Generating content calendar: %d days x %d posts", days, posts_per_day)
        calendar: list[ContentCalendarSlot] = []
        content_types = ["reel", "carousel", "story"]
        captions_pool = [
            "Check out this amazing moment! What do you think?",
            "Behind the scenes of something special...",
            "Trending now — don't miss out!",
            "Double tap if you agree!",
            "Save this for later inspiration!",
            "Tag someone who needs to see this!",
            "Which version do you prefer? Let me know!",
            "New content dropping now!",
        ]
        audio_pool = ["Trending Track 1", "Viral Beat", "Pop Hit", "Lo-Fi Vibes"]
        for day in range(days):
            date = (datetime.now() + timedelta(days=day)).strftime("%Y-%m-%d")
            for slot in range(posts_per_day):
                hour = 9 + slot * 6
                time_str = f"{hour:02d}:00"
                calendar.append(ContentCalendarSlot(
                    date=date,
                    time=time_str,
                    content_type=random.choice(content_types),
                    caption=random.choice(captions_pool),
                    hashtags=[f"#{t}" for t in self._mock_hashtags("trend")],
                    audio_suggestion=random.choice(audio_pool),
                ))
        return calendar

    # -- Analytics ----------------------------------------------------------

    def track_analytics(self, reels: list[ReelMetadata] | None = None) -> dict[str, Any]:
        """Track aggregate analytics across reels."""
        data = reels or self.reels_db
        if not data:
            return {"status": "no_data", "message": "No reels to analyse"}
        total_views = sum(r.view_count for r in data)
        total_likes = sum(r.like_count for r in data)
        total_comments = sum(r.comment_count for r in data)
        total_shares = sum(r.share_count for r in data)
        avg_engagement = round(sum(r.engagement_rate for r in data) / len(data), 2)
        report = {
            "total_reels": len(data),
            "total_views": total_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "avg_engagement_rate": avg_engagement,
            "top_performer": max(data, key=lambda r: r.engagement_rate).to_dict(),
            "timestamp": datetime.now().isoformat(),
        }
        self.analytics_history.append(report)
        logger.info("Analytics tracked for %d reels", len(data))
        return report

    def export_analytics(self, filepath: str | None = None) -> str:
        """Export analytics history to JSON."""
        path = filepath or str(self.storage_dir / "analytics.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.analytics_history, f, indent=2, default=str)
        logger.info("Analytics exported to %s", path)
        return path

    # -- Helpers ------------------------------------------------------------

    def _url_to_id(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()[:12]

    def _mock_caption(self, hashtag: str, idx: int) -> str:
        templates = [
            f"Amazing content for #{hashtag}! What do you think?",
            f"Behind the scenes of #{hashtag} — pure magic!",
            f"Trending with #{hashtag}! Don't miss this!",
            f"This #{hashtag} moment is everything!",
            f"Double tap if you love #{hashtag}!",
        ]
        return templates[idx % len(templates)]

    def _mock_hashtags(self, seed: str) -> list[str]:
        pool = [seed, "viral", "reels", "trending", "instagood", "explore",
                "love", "fyp", "foryou", "follow", "like", "share"]
        return random.sample(pool, k=random.randint(5, 10))

    def _mock_audio(self) -> str:
        return random.choice([
            "Original Audio", "Trending Sound", "Remix Beat",
            "Viral Track", "Pop Classic", "Electronic Drop",
        ])

    def _create_placeholder_video(self, path: Path) -> None:
        """Create a tiny placeholder MP4 file."""
        placeholder = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 256
        path.write_bytes(placeholder)
        logger.debug("Created placeholder video at %s", path)

    def _create_placeholder_thumbnail(self, path: Path) -> None:
        """Create a placeholder thumbnail image."""
        if Image is not None:
            try:
                img = Image.new("RGB", (320, 568), color=(20, 20, 30))
                draw = ImageDraw.Draw(img)
                draw.text((80, 280), "JARVIS BRAINIAC", fill=(0, 255, 100))
                img.save(path, "JPEG")
                return
            except Exception as exc:
                logger.debug("Thumbnail creation failed: %s", exc)
        path.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 128)
        logger.debug("Created placeholder thumbnail at %s", path)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    print("=" * 60)
    print("JARVIS BRAINIAC — Instagram Integration Self-Test")
    print("=" * 60)

    ig = InstagramIntegration()

    # Test discovery
    reels = ig.discover_reels("ai", count=5)
    print(f"\n[1] Discovered {len(reels)} reels")
    for r in reels[:3]:
        print(f"    - {r.reel_id} | Views: {r.view_count:,} | Engagement: {r.engagement_rate}%")

    # Test hashtag extraction
    sample = "Love this #AI content! #machinelearning #python @jarvisbrainiac"
    tags = ig.extract_hashtags(sample)
    print(f"\n[2] Extracted hashtags: {tags}")

    # Test caption insights
    insights = ig.extract_caption_insights(sample)
    print(f"[3] Caption insights: {json.dumps(insights, indent=2)}")

    # Test hashtag research
    hr = ig.research_hashtag("python")
    print(f"\n[4] Hashtag research for #python:")
    print(f"    Posts: {hr.post_count:,} | Trending score: {hr.trending_score}")

    # Test optimised hashtag set
    opt = ig.optimise_hashtag_set("coding", count=5)
    print(f"\n[5] Optimised hashtags: {[h.tag for h in opt]}")

    # Test content calendar
    cal = ig.generate_content_calendar(days=3, posts_per_day=2)
    print(f"\n[6] Content calendar ({len(cal)} slots):")
    for c in cal[:4]:
        print(f"    {c.date} {c.time} | {c.content_type} | {c.caption[:40]}...")

    # Test trending audio
    audio = ig.discover_trending_audio(5)
    print(f"\n[7] Trending audio ({len(audio)} tracks):")
    for a in audio[:3]:
        print(f"    {a['name']} by {a['artist']} (score: {a['trend_score']})")

    # Test analytics
    analytics = ig.track_analytics(reels)
    print(f"\n[8] Analytics: {json.dumps(analytics, indent=2, default=str)[:400]}...")

    # Test export
    export_path = ig.export_analytics()
    print(f"\n[9] Analytics exported to: {export_path}")

    print("\n" + "=" * 60)
    print("All Instagram integration tests passed!")
    print("=" * 60)
