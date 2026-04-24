import json
import unittest

import numpy as np

from surveillance.events.store import EventStore
from surveillance.json_utils import to_jsonable


class JsonUtilsTests(unittest.TestCase):
    def test_to_jsonable_converts_numpy_scalars_and_arrays(self):
        payload = {
            "value": np.int64(7),
            "score": np.float32(0.5),
            "bbox": np.array([1, 2, 3, 4], dtype=np.int64),
        }

        converted = to_jsonable(payload)

        self.assertEqual(converted["value"], 7)
        self.assertEqual(converted["bbox"], [1, 2, 3, 4])
        json.dumps(converted)

    def test_event_store_output_is_json_serializable(self):
        store = EventStore()
        store.record(
            "face_recognized",
            camera_name="cam1",
            payload={
                "bbox": [np.int64(10), np.int64(20), np.int64(30), np.int64(40)],
                "person_id": np.int64(3),
            },
        )

        payload = store.list_events(limit=5)
        json.dumps(payload)


if __name__ == "__main__":
    unittest.main()
