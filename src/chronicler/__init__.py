"""AI-driven civilization chronicle generator."""
import os

# NumPy's bundled OpenBLAS keeps its worker threads spinning for 2^28 cycles
# (about 0.1 s) after every threaded call. Civs above 10,000 agents reach the
# threaded dot product (``agent_bridge.compute_gini``), and the spinning threads
# then burn CPU, competing with the turn itself, until the next call. A short
# spin keeps the thread count, the work split and therefore every result
# unchanged. OpenBLAS reads the variable when NumPy loads; a value set by the
# user is kept.
os.environ.setdefault("OPENBLAS_THREAD_TIMEOUT", "16")
