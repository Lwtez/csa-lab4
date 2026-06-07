import os
import sys

# Кладём корень репозитория в sys.path, чтобы из tests/ работало
# `import translator, machine, isa`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
