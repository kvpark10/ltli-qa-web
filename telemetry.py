"""Compatibility stubs. LTLI collects no behavioral telemetry."""
import time
APP_VERSION='public-qa-1'
def elapsed_milliseconds(started): return int((time.perf_counter()-started)*1000)
def file_size_bucket(size): return 'disabled'
def telemetry_enabled(): return False
def track_event(*args,**kwargs): return None
def track_once(*args,**kwargs): return None
