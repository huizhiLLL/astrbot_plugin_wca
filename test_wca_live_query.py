import sys
import types
import unittest


api = types.ModuleType("astrbot.api")
api.logger = types.SimpleNamespace(warning=lambda *args, **kwargs: None)
star = types.ModuleType("astrbot.api.star")
star.StarTools = object
event = types.ModuleType("astrbot.api.event")
event.AstrMessageEvent = object
sys.modules.setdefault("astrbot", types.ModuleType("astrbot"))
sys.modules.setdefault("astrbot.api", api)
sys.modules.setdefault("astrbot.api.star", star)
sys.modules.setdefault("astrbot.api.event", event)

from data.plugins.astrbot_plugin_wca.core.wca_live_query import WCALiveQuery


class LiveMergeTests(unittest.TestCase):
    def test_preserves_official_averages_without_live_average(self):
        official = {
            "single_records": [{"event_id": "222", "best": 402}],
            "average_records": [{"event_id": "222", "best": 575}],
        }
        merged = WCALiveQuery._merge_records(official, [])
        self.assertEqual(merged["average_records"][0]["best"], 575)

    def test_prefers_the_best_average_across_all_live_rounds(self):
        official = {
            "single_records": [{"event_id": "333oh", "best": 1478}],
            "average_records": [{"event_id": "333oh", "best": 1781}],
        }
        live = [
            {"event_id": "333oh", "best": 1181, "average": 1281},
            {"event_id": "333oh", "best": 1054, "average": 1326},
        ]
        merged = WCALiveQuery._merge_records(official, live)
        self.assertEqual(merged["single_records"][0]["best"], 1054)
        self.assertEqual(merged["average_records"][0]["best"], 1281)


if __name__ == "__main__":
    unittest.main()
