"""Tests for parallel dimension processing in Step 4."""
import os
import sys
import argparse
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test API keys before importing
os.environ['OPENAI_API_KEY'] = 'sk-test-primary-key-000000'
os.environ['OPENAI_API_KEY_1'] = 'sk-test-key-1-000000'
os.environ['OPENAI_API_KEY_2'] = 'sk-test-key-2-000000'
os.environ.pop('OPENAI_API_KEY_3', None)


class TestMultiApiKeys(unittest.TestCase):
    
    def test_load_all_api_keys_finds_all(self):
        from model_definitions import load_all_api_keys
        keys = load_all_api_keys()
        self.assertEqual(len(keys), 3)
        self.assertIn('sk-test-primary-key-000000', keys)
        self.assertIn('sk-test-key-1-000000', keys)
        self.assertIn('sk-test-key-2-000000', keys)
    
    def test_load_all_api_keys_deduplicates(self):
        """If OPENAI_API_KEY and OPENAI_API_KEY_1 are the same, only one entry."""
        os.environ['OPENAI_API_KEY_1'] = 'sk-test-primary-key-000000'  # Same as primary
        from model_definitions import load_all_api_keys
        keys = load_all_api_keys()
        # Count occurrences of primary key
        count = sum(1 for k in keys if k == 'sk-test-primary-key-000000')
        self.assertEqual(count, 1)
        # Restore
        os.environ['OPENAI_API_KEY_1'] = 'sk-test-key-1-000000'
    
    def test_create_openai_client(self):
        from model_definitions import create_openai_client
        client = create_openai_client('sk-test-key')
        self.assertEqual(type(client).__name__, 'OpenAI')
    
    def test_create_dim_args_own_client(self):
        from main2 import create_dim_args
        args = argparse.Namespace(llm='gpt', client={'gpt': 'original_client'})
        dim_args = create_dim_args(args, 'sk-test-key')
        # Should have its own OpenAI client
        self.assertEqual(type(dim_args.client['gpt']).__name__, 'OpenAI')
        # Original should be unchanged
        self.assertEqual(args.client['gpt'], 'original_client')
    
    def test_create_dim_args_no_key_reuses_client(self):
        from main2 import create_dim_args
        args = argparse.Namespace(llm='gpt', client={'gpt': 'shared_client'})
        dim_args = create_dim_args(args, api_key=None)
        # Should reuse the original client
        self.assertEqual(dim_args.client['gpt'], 'shared_client')
    
    def test_create_dim_args_copies_other_attrs(self):
        from main2 import create_dim_args
        args = argparse.Namespace(
            llm='gpt', client={'gpt': 'x'}, 
            max_depth=4, max_density=15, topic='test', data_dir='/tmp'
        )
        dim_args = create_dim_args(args, 'sk-key')
        self.assertEqual(dim_args.max_depth, 4)
        self.assertEqual(dim_args.max_density, 15)
        self.assertEqual(dim_args.topic, 'test')


class TestParallelStep4Structure(unittest.TestCase):
    
    def test_step4_parallel_function_exists(self):
        from main2 import step4_parallel
        self.assertTrue(callable(step4_parallel))
    
    def test_step4_process_single_dimension_exists(self):
        from main2 import step4_process_single_dimension
        self.assertTrue(callable(step4_process_single_dimension))
    
    def test_round_robin_key_assignment(self):
        """Test that keys are assigned round-robin to dimensions."""
        from model_definitions import load_all_api_keys
        keys = load_all_api_keys()
        dimensions = ['dim_a', 'dim_b', 'dim_c', 'dim_d', 'dim_e']
        
        assignments = {}
        for i, dim in enumerate(dimensions):
            key_idx = i % len(keys)
            assignments[dim] = key_idx
        
        # With 3 keys and 5 dims: 0,1,2,0,1
        self.assertEqual(assignments['dim_a'], 0)
        self.assertEqual(assignments['dim_b'], 1)
        self.assertEqual(assignments['dim_c'], 2)
        self.assertEqual(assignments['dim_d'], 0)
        self.assertEqual(assignments['dim_e'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
