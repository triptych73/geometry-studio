import unittest
import time
from staircase_structural import build_structural_staircase, DEFAULT_CONFIG

class TestStructuralBuilder(unittest.TestCase):
    def test_default_config_generation(self):
        print("\nTesting DEFAULT_CONFIG...")
        start_time = time.time()
        result = build_structural_staircase(DEFAULT_CONFIG)
        duration = time.time() - start_time
        
        self.assertIsNotNone(result)
        self.assertIn('treads', result)
        self.assertIn('risers', result)
        self.assertIn('stringers', result)
        self.assertIn('plaster', result)
        
        print(f"Generated {len(result['treads'])} treads, "
              f"{len(result['stringers'])} stringers, "
              f"{len(result['plaster'])} plaster shell(s) in {duration:.2f}s")
              
    def test_straight_flight_only(self):
        print("\nTesting straight flight (no winders)...")
        config = DEFAULT_CONFIG.copy()
        config['s_bottom_steps'] = 14
        config['winder_steps'] = 0
        config['s_top_steps'] = 0
        
        result = build_structural_staircase(config)
        self.assertIsNotNone(result)
        # Should have exactly 2 stringers (left and right for one flight)
        self.assertEqual(len(result['stringers']), 3)
        
    def test_winder_only(self):
        print("\nTesting winder only...")
        config = DEFAULT_CONFIG.copy()
        config['s_bottom_steps'] = 0
        config['winder_steps'] = 3
        config['s_top_steps'] = 0
        
        result = build_structural_staircase(config)
        self.assertIsNotNone(result)
        # Winder corner stringers
        self.assertGreater(len(result['stringers']), 0)

if __name__ == '__main__':
    unittest.main()
