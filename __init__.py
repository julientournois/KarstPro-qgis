# Copyright (c) 2026 Julien Tournois
# Licence : PolyForm Noncommercial License 1.0.0
# Usage commercial interdit sans autorisation écrite — julien.tournois@gmail.com
# https://polyformproject.org/licenses/noncommercial/1.0.0
import sys
import io


class _SafeStream:
    """Null stream that silently absorbs writes.

    QGIS sets sys.stdout/stderr to None during plugin loading, which crashes
    numpy, whitebox and other C-extensions that write deprecation warnings.
    This safe fallback prevents those crashes without polluting any real output.
    """
    def write(self, *args, **kwargs):
        pass

    def flush(self, *args, **kwargs):
        pass

    def fileno(self):
        raise io.UnsupportedOperation("fileno")


# Patch unconditionally at module level — QGIS may reset these to None at any
# point during startup. We replace None with a safe no-op stream; real streams
# are left untouched so normal output still works.
if sys.stdout is None:
    sys.stdout = _SafeStream()
if sys.stderr is None:
    sys.stderr = _SafeStream()

# Belt-and-suspenders: install a module __getattr__ so that if QGIS resets
# sys.stderr/stdout to None AFTER this module runs, the patch re-applies on
# any subsequent attribute access (Python 3.7+).
def _ensure_streams():
    if sys.stdout is None:
        sys.stdout = _SafeStream()
    if sys.stderr is None:
        sys.stderr = _SafeStream()


def classFactory(iface):
    """QGIS plugin entry point."""
    _ensure_streams()  # re-apply patch in case QGIS reset streams after module load
    from karstpro.karstpro_plugin import KarstProPlugin
    return KarstProPlugin(iface)
