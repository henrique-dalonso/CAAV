import sys
from pathlib import Path

# Garante que "app" seja importável independente de como o pytest for chamado.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
