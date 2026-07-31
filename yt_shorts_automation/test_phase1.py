import unittest
from src.highlight_engine import _parse_candidate_list, refine_boundaries
from src.captioner import _group_words_karaoke

class TestPhase1(unittest.TestCase):
    def test_parse_candidate_list(self):
        raw_json = """```json
[
  {
    "start": 10.5,
    "end": 25.0,
    "hook_line": "This is a hook",
    "hook_type": "question",
    "payoff_type": "insight",
    "rationale": "Because",
    "self_contained": true
  }
]
```"""
        parsed = _parse_candidate_list(raw_json)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["start"], 10.5)
        self.assertEqual(parsed[0]["end"], 25.0)
        self.assertEqual(parsed[0]["hook_line"], "This is a hook")

    def test_refine_boundaries(self):
        segments = [
            {"start": 10.0, "end": 15.0, "words": [
                {"start": 10.0, "end": 11.0, "word": "Hello"},
                {"start": 11.5, "end": 12.0, "word": "world"} # gap of 0.5s > 300ms
            ]}
        ]
        candidates = [{"start": 11.2, "end": 20.0, "hook_line": "Test"}]
        
        refined = refine_boundaries(candidates, segments)
        
        self.assertEqual(len(refined), 1)
        self.assertEqual(refined[0]["start"], 11.0)

    def test_group_words_karaoke(self):
        words = [
            {"start": 0, "end": 1, "word": "One"},
            {"start": 1, "end": 2, "word": "two"},
            {"start": 2, "end": 3, "word": "three"},
            {"start": 3, "end": 4, "word": "four"},
            {"start": 4, "end": 5, "word": "five"}
        ]
        chunks = _group_words_karaoke(words, max_chars=35, max_words=4)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chunks[0]), 4)
        self.assertEqual(len(chunks[1]), 1)
        
    def test_smooth_trajectory(self):
        from src.clipper import smooth_trajectory
        src_w, src_h = 1000, 1000
        # Jump from 500 to 900 (diff 400). Max pan is 5% of 1000 = 50.
        raw = [(500, 500), (900, 500)]
        smoothed = smooth_trajectory(raw, src_w, src_h)
        
        self.assertEqual(smoothed[0], (500, 500))
        # It should move by at most 50
        self.assertTrue(smoothed[1][0] <= 550)
        self.assertEqual(smoothed[1][1], 500)
        
if __name__ == "__main__":
    unittest.main()
