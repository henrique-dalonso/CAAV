from concurrent.futures import ProcessPoolExecutor


_executor = None


def _obter_executor():
    """Ver docstring equivalente em app/ferramentas/extratus/core/
    pdf_isolado.py (Extratus - Relatórios) — mesma lógica."""
    global _executor

    if _executor is None:
        _executor = ProcessPoolExecutor(max_workers=2)

    return _executor


def executar_isolado(funcao, *args):
    """Ver docstring equivalente em app/ferramentas/extratus/core/
    pdf_isolado.py (Extratus - Relatórios) — mesmo bug real (GIL do
    pypdf), mesma correção, compartilhado entre checagem_lote.py e
    robo_lote.py."""
    return _obter_executor().submit(funcao, *args).result()
