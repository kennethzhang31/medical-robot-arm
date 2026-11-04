import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from env.instrument_materials import INSTRUMENT_MATERIAL_OVERRIDES


class InstrumentMaterialContractTests(unittest.TestCase):
    def test_only_source_asset_without_material_gets_override(self):
        self.assertEqual(set(INSTRUMENT_MATERIAL_OVERRIDES), {"scissor"})

    def test_scissor_fallback_is_readable_brushed_metal(self):
        material = INSTRUMENT_MATERIAL_OVERRIDES["scissor"]
        self.assertEqual(len(material.diffuse_color), 3)
        self.assertTrue(all(0.0 <= channel <= 1.0 for channel in material.diffuse_color))
        self.assertGreater(material.metallic, 0.5)
        self.assertGreaterEqual(material.roughness, 0.25)
        self.assertLessEqual(material.roughness, 0.6)
        self.assertAlmostEqual(material.roughness, 0.52)


if __name__ == "__main__":
    unittest.main()
