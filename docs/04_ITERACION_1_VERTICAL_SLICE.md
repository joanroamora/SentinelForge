# Iteración 1 — vertical slice de demostración

## Qué demuestra

CLI, API HTTP y una página HTML llaman al mismo `AnalysisService`. El servicio genera un reporte sintético con contrato Pydantic versionado; no inspecciona ni ejecuta código del usuario. La evidencia se marca como simulada y la declaración humana como `unverified`.

## Piezas

- `contracts.py`: formas y estados permitidos para análisis, hallazgos, evidencia y declaraciones.
- `service.py`: lógica de aplicación compartida y almacenamiento temporal en memoria.
- `cli.py`: adaptador de terminal que serializa el reporte como JSON.
- `api.py`: adaptador HTTP y página de demostración servida por FastAPI.
- `tests/`: comprueba estados del contrato, endpoints, errores 404, HTML y equivalencia entre CLI y API.

## Cómo ejecutar en Windows PowerShell

Con Python 3.11 o posterior disponible:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\sentinelforge.exe demo
.\.venv\Scripts\python.exe -m uvicorn sentinelforge.api:app --reload
```

La web queda en `http://127.0.0.1:8000/`; la API en `http://127.0.0.1:8000/docs`.

## Cómo ejecutar en Linux o macOS

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e '.[dev]'
./.venv/bin/python -m pytest
./.venv/bin/sentinelforge demo
./.venv/bin/python -m uvicorn sentinelforge.api:app --reload
```

## Límites y aprendizaje

Los reportes solo viven en memoria y desaparecen al reiniciar el proceso. No hay autenticación, persistencia, escáner, agente LLM ni ejecución aislada. Una virtualenv aísla dependencias de Python, pero no es un sandbox para código no confiable. En esta fase se prueba el contrato del producto, no su capacidad para detectar vulnerabilidades.
