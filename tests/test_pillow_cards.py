import io
import unittest

from PIL import Image

from astrbot_plugin_wca.core.pillow_cards import (
    render_cube_help_card,
    render_wca_person_card,
)


class PillowCardsTest(unittest.TestCase):
    def test_render_cube_help_card_returns_valid_image(self):
        data = {
            "title": "Cube 命令帮助",
            "subtitle": "WCA 与 one 相关命令一览",
            "commands": [
                {"name": "/wca", "desc": "查询 WCA 个人成绩", "example": "/wca 李华"},
                {"name": "/wcapic", "desc": "生成 WCA 个人纪录图片", "example": "/wcapic 李华"},
                {"name": "/pktwo", "desc": "双平台 PK", "example": "/pktwo 2026LIHU01 2558"},
            ],
        }

        image_bytes = render_cube_help_card(data)

        self.assertGreater(len(image_bytes), 5000)
        with Image.open(io.BytesIO(image_bytes)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertGreaterEqual(image.size[0], 1000)
            self.assertGreaterEqual(image.size[1], 600)

    def test_render_wca_person_card_returns_valid_image(self):
        records_data = {
            "person": {
                "name": "李华",
                "wca_id": "2026LIHU01",
                "country_iso2": "CN",
                "country_name": "China",
                "gender": "m",
                "avatar_thumb_url": "",
            },
            "competition_count": 12,
            "total_solves": 345,
            "single_records": [
                {
                    "event_id": "333",
                    "event_name": "3x3x3 Cube",
                    "event_rank": 1,
                    "event_format": "time",
                    "best": 812,
                    "country_rank": 15,
                    "continent_rank": 52,
                    "world_rank": 233,
                },
                {
                    "event_id": "333oh",
                    "event_name": "3x3x3 One-Handed",
                    "event_rank": 2,
                    "event_format": "time",
                    "best": 1765,
                    "country_rank": 25,
                    "continent_rank": 80,
                    "world_rank": 355,
                },
            ],
            "average_records": [
                {
                    "event_id": "333",
                    "event_name": "3x3x3 Cube",
                    "event_rank": 1,
                    "event_format": "time",
                    "best": 1025,
                    "country_rank": 12,
                    "continent_rank": 48,
                    "world_rank": 210,
                }
            ],
        }

        image_bytes = render_wca_person_card(records_data)

        self.assertGreater(len(image_bytes), 8000)
        with Image.open(io.BytesIO(image_bytes)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertGreaterEqual(image.size[0], 1100)
            self.assertGreaterEqual(image.size[1], 900)


if __name__ == "__main__":
    unittest.main()
