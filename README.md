# HoodIntel scaffold

This is a refactor scaffold that breaks the original all-in-one script into a real package layout:

- `src/config.py` - settings, API key block, defaults
- `src/models.py` - dataclasses shared across the app
- `src/collectors/` - source-specific fetchers
- `src/analysis/` - summary + hardening recommendations
- `src/renderers/` - PDF/JSON output
- `src/pipeline.py` - orchestration
- `hoodintel.py` - thin CLI entrypoint

## Run

```bash
python -m pip install -r requirements.txt
python hoodintel.py "7978 Canton Dr, Lemon Grove, CA 91945" --json-out out.json
```
