import sys
import os
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

# Ensure we can import instaloader
sys.path.insert(0, os.getcwd())

from instaloader.instaloader import _ArbitraryItemFormatter, PostSidecarNode, Post
from instaloader.structures import PostSidecarNode as StructPostSidecarNode

class TestNewFeatures(unittest.TestCase):
    def test_timezone_formatting(self):
        # Mock object with date_utc
        class MockItem:
            date_utc = datetime(2023, 1, 1, 12, 0, 0)
            date_local = datetime(2023, 1, 1, 12, 0, 0)
            date = date_utc
            
        item = MockItem()
        formatter = _ArbitraryItemFormatter(item)
        
        # Test {date} (default UTC)
        self.assertEqual(formatter.format("{date:%H}"), "12")
        
        # Test {date+5} (UTC + 5 hours) -> 17:00
        self.assertEqual(formatter.format("{date+5:%H}"), "17")
        
        # Test {date-5} (UTC - 5 hours) -> 07:00
        self.assertEqual(formatter.format("{date-5:%H}"), "07")
        
        # Test {date_utc+1}
        self.assertEqual(formatter.format("{date_utc+1:%H}"), "13")

    def test_fileId_placeholder(self):
        # Mock Post
        post = MagicMock(spec=Post)
        post_formatter = _ArbitraryItemFormatter(post)
        
        # Post should return literal {fileId}
        self.assertEqual(post_formatter.format("test_{fileId}"), "test_{fileId}")
        
        # Mock SidecarNode
        # Note: PostSidecarNode is a NamedTuple, so we can't MagicMock it easily to act like one.
        # We use the actual class.
        node = StructPostSidecarNode(is_video=False, display_url="url", video_url=None, id="12345")
        node_formatter = _ArbitraryItemFormatter(node)
        
        # SidecarNode should return id
        # Wait, my logic in get_value for PostSidecarNode returns self._item.id
        # But _ArbitraryItemFormatter logic:
        # if key == 'fileId' and isinstance(self._item, PostSidecarNode): return self._item.id
        self.assertEqual(node_formatter.format("{fileId}"), "12345")

    def test_sidecar_node_structure(self):
        # Verify PostSidecarNode has id field
        node = StructPostSidecarNode(is_video=False, display_url="url", video_url=None, id="test_id")
        self.assertEqual(node.id, "test_id")

    def test_fallback_syntax(self):
        # Test {fileId|mediaid} for Post - should preserve literal for later replacement
        post = MagicMock(spec=Post)
        post.mediaid = 123456789
        post_formatter = _ArbitraryItemFormatter(post)
        self.assertEqual(post_formatter.format("{fileId|mediaid}"), "{fileId|mediaid}")

        # Test {fileId|mediaid} for SidecarNode (fileId available, should use fileId)
        node = StructPostSidecarNode(is_video=False, display_url="url", video_url=None, id="99999")
        node_formatter = _ArbitraryItemFormatter(node)
        self.assertEqual(node_formatter.format("{fileId|mediaid}"), "99999")

        # Test multi-level fallback {a|b|c} for non-fileId cases
        class MockItem:
            c = "fallback_c"
        item = MockItem()
        formatter = _ArbitraryItemFormatter(item)
        self.assertEqual(formatter.format("{a|b|c}"), "fallback_c")

        # Test all fallbacks invalid - returns literal
        self.assertEqual(formatter.format("{x|y|z}"), "{x|y|z}")

    def test_target_base_placeholder(self):
        # Test target_base with tagged posts path
        class MockItem:
            pass
        item = MockItem()
        formatter = _ArbitraryItemFormatter(item)

        # Test username/:tagged -> username
        self.assertEqual(formatter.format("{target_base}", target="mm.91_/:tagged"), "mm.91_")

        # Test hashtag with # prefix
        self.assertEqual(formatter.format("{target_base}", target="#hashtag"), "hashtag")

        # Test feed with : prefix
        self.assertEqual(formatter.format("{target_base}", target=":feed"), "feed")

        # Test location with % prefix
        self.assertEqual(formatter.format("{target_base}", target="%12345"), "12345")

        # Test plain username
        self.assertEqual(formatter.format("{target_base}", target="username"), "username")

        # Test with Path object
        from pathlib import Path
        self.assertEqual(formatter.format("{target_base}", target=Path("mm.91_") / ":tagged"), "mm.91_")

if __name__ == '__main__':
    unittest.main()
