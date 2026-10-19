"""Refresh the standalone notebook's bundled engine after editing migration_sim.py.

Run: python notebooks/en/repoMigrationSim/sync_notebook.py
The notebook embeds the engine so opening only sim.ipynb in Colab is sufficient.
"""
import json
from pathlib import Path


def sync_notebook():
    folder = Path(__file__).resolve().parent
    path = folder / 'sim.ipynb'
    notebook = json.loads(path.read_text(encoding='utf-8'))
    source = (
        '# @title Simulation engine (bundled; run once)\n'
        '# Generated from migration_sim.py by sync_notebook.py.\n'
        '# Edit the module and run the sync script to refresh this cell.\n\n'
        + (folder / 'migration_sim.py').read_text(encoding='utf-8')
    )
    engine = next((c for c in notebook['cells'] if c['id'] == 'migration-engine'), None)
    if engine is None:
        engine = {
            'cell_type': 'code', 'id': 'migration-engine',
            'metadata': {'jupyter': {'source_hidden': True}, 'cellView': 'form'},
            'execution_count': None, 'outputs': [], 'source': [],
        }
        index = next(i for i, c in enumerate(notebook['cells']) if c['id'] == 'migration-03')
        notebook['cells'].insert(index, engine)
    engine['source'] = source.splitlines(keepends=True)
    engine['execution_count'] = None
    engine['outputs'] = []
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    sync_notebook()
