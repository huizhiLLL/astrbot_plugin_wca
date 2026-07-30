import unittest

from core.wca_formatting import _rank_label


class RankLabelTests(unittest.TestCase):
    def test_chinese_world_record_wins_three_way_first_place_tie(self):
        self.assertEqual(_rank_label("CN", 1, 1, 1), "WR")

    def test_chinese_continent_record_wins_two_way_first_place_tie(self):
        self.assertEqual(_rank_label("CN", 2, 1, 1), "CR")

    def test_chinese_equal_non_record_ranks_use_scope_priority(self):
        self.assertEqual(_rank_label("CN", 2, 2, 2), "WR2")

    def test_chinese_best_numeric_rank_wins(self):
        self.assertEqual(_rank_label("CN", 8, 5, 3), "NR3")

    def test_chinese_rank_limit_is_preserved(self):
        self.assertEqual(_rank_label("CN", 201, 202, 203), "-")

    def test_non_chinese_priority_is_unchanged(self):
        self.assertEqual(_rank_label("US", 101, 2, 1), "CR2")


if __name__ == "__main__":
    unittest.main()
