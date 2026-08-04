import unittest

from abk.adapters import youtube as yt
from abk.domain import TranscriptUnavailable


class TestYouTubeTranscriber(unittest.TestCase):
    def setUp(self):
        self.t = yt.YouTubeTranscriber()
        self._caps, self._meta, self._link = yt.fetch_captions, yt.fetch_page_meta, yt.follow_recipe_link

    def tearDown(self):
        yt.fetch_captions, yt.fetch_page_meta, yt.follow_recipe_link = self._caps, self._meta, self._link

    def test_rejects_non_youtube_url(self):
        with self.assertRaises(TranscriptUnavailable):
            self.t.fetch("https://example.com/not-a-video")

    def test_uses_captions_when_available(self):
        yt.fetch_captions = lambda vid: "c" * 400
        yt.fetch_page_meta = lambda url: (_ for _ in ()).throw(AssertionError("should not fetch page"))
        self.assertEqual(len(self.t.fetch("https://youtu.be/ABCDEFGHIJK")), 400)

    def test_falls_back_to_description_when_no_captions(self):
        yt.fetch_captions = lambda vid: (_ for _ in ()).throw(Exception("disabled"))
        yt.fetch_page_meta = lambda url: ("Paneer Butter Masala", "d" * 400)
        yt.follow_recipe_link = lambda d: ""
        out = self.t.fetch("https://youtu.be/ABCDEFGHIJK")
        self.assertIn("NAME: Paneer Butter Masala", out)

    def test_follows_linked_recipe_page(self):
        yt.fetch_captions = lambda vid: ""
        yt.fetch_page_meta = lambda url: ("Title", "full recipe: https://site.com/r")
        yt.follow_recipe_link = lambda d: "ingredients: paneer, butter " * 20
        self.assertIn("ingredients", self.t.fetch("https://youtu.be/ABCDEFGHIJK"))

    def test_raises_when_everything_is_empty(self):
        yt.fetch_captions = lambda vid: ""
        yt.fetch_page_meta = lambda url: ("", "")
        yt.follow_recipe_link = lambda d: ""
        with self.assertRaises(TranscriptUnavailable):
            self.t.fetch("https://youtu.be/ABCDEFGHIJK")

    def test_skips_social_links(self):
        self.assertEqual(yt.follow_recipe_link("see https://instagram.com/x"), "")


if __name__ == "__main__":
    unittest.main()
