"""Portable peak process memory receipt without changing host limits."""
import sys


def peak_ram_mib():
    try:
        import resource
        value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value/(1024**2 if sys.platform=='darwin' else 1024)
    except ImportError:
        try:
            import psutil
            memory=psutil.Process().memory_info()
            return memory.peak_wset/1024**2 if hasattr(memory,'peak_wset') else None
        except ImportError:
            return None
