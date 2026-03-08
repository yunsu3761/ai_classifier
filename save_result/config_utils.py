#!/usr/bin/env python
"""
Utility functions to load configuration from YAML files
"""
import yaml
import threading
from pathlib import Path
import os

# Global override: set these from web_interface to inject config dynamically
# Thread-safe per-thread storage to avoid cross-user contamination in multi-session Streamlit
_config_lock = threading.Lock()
_override_dimensions_by_thread = {}
_override_korean_names_by_thread = {}

def set_override_config(dimensions=None, korean_names=None):
    """Set override dimensions and korean names from web interface (thread-safe)"""
    tid = threading.get_ident()
    with _config_lock:
        if dimensions is not None:
            _override_dimensions_by_thread[tid] = dimensions
        if korean_names is not None:
            _override_korean_names_by_thread[tid] = korean_names

def clear_override_config():
    """Clear override config for current thread"""
    tid = threading.get_ident()
    with _config_lock:
        _override_dimensions_by_thread.pop(tid, None)
        _override_korean_names_by_thread.pop(tid, None)

def _get_override_dimensions():
    """Get override dimensions for current thread"""
    tid = threading.get_ident()
    with _config_lock:
        return _override_dimensions_by_thread.get(tid)

def _get_override_korean_names():
    """Get override korean names for current thread"""
    tid = threading.get_ident()
    with _config_lock:
        return _override_korean_names_by_thread.get(tid)

def load_config(config_file=None):
    """Load configuration from YAML file"""
    if config_file is None:
        # Default to example_electrical_steel.yaml
        base_dir = Path(__file__).parent
        config_file = base_dir / 'configs' / 'example_battery.yaml'
    
    config_file = Path(config_file)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config

def get_dimensions(config_file=None):
    """Get dimension definitions from config file"""
    override = _get_override_dimensions()
    if override is not None:
        return override
    config = load_config(config_file)
    return config.get('dimensions', {})

def get_dimension_names_korean():
    """Get Korean dimension names mapping"""
    override = _get_override_korean_names()
    if override is not None:
        return override
    return {
        'cathode_material': '양극재',
        'anode_material': '음극재',
        'solid_electrolyte': '고체전해질',
        'recycling': '리싸이클링',
        'lithium': '리튬'
    }

def get_dimension_names_english():
    """Get English dimension names mapping (for backward compatibility)"""
    dimensions = get_dimensions()
    return {dim: dim.replace('_', ' ').title() for dim in dimensions.keys()}