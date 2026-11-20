# SentinelForge AI

**Multi-Agent Security Analysis Platform**  
**Estado:** definición inicial (no existe aún un motor de escaneo funcional).

## Misión

SentinelForge AI analiza artefactos de software autorizados (código, dependencias, Docker e infraestructura como código), investiga hallazgos con subagentes especializados, efectúa verificaciones independientes y produce informes auditables. El producto se usa desde:

- **CLI local / CI-CD / runners:** ejecución no interactiva, reporte en JSON y SARIF; opcionalmente envía el análisis al servidor.
- **API HTTP:** entrada común para artefactos, eventos, preguntas, aportes humanos e informes.
- **Interfaz web:** panel de análisis, revisión de evidencias y diálogo con el modo Monitor.

Las tres interfaces **comparten modelos, reglas de negocio y motor de análisis**; no implementan tres motores distintos.

## Principios de producto

1. **Evidencia antes que opinión:** los agentes no inventan pruebas de explotabilidad.
2. **Los aportes humanos pertenecen al informe:** se almacenan y citan como declaraciones del usuario, con autoría, fecha, contenido y estado de verificación. Su inclusión no implica verificación automática.
3. **Falsos positivos y negativos medibles:** el objetivo no es suprimir alertas, sino priorizarlas y justificar cada decisión.
4. **No ejecutar artefactos no confiables** sin una infraestructura de aislamiento específica, aprobada y probada.
5. **Offline-first para el núcleo local:** el MVP puede funcionar con un analizador ficticio/determinista y sin API keys. Servicios LLM y escáneres reales se agregan por adaptadores controlados.
6. **Sin instalaciones globales de paquetes Python:** usar siempre `.venv` y el intérprete de ese entorno.

## Alcance inicial del MVP

Un flujo vertical demostrable: un proyecto Python de prueba es recibido por CLI o API; se genera una señal de hallazgo de una fixture controlada; el orquestador solicita evidencia a subagentes de investigación y verificación; se formula una pregunta humana; la respuesta queda registrada, afecta la evaluación de contexto sin convertirse automáticamente en prueba; se emite un reporte con evidencias y limitaciones.

**Fuera del MVP:** escaneo activo no autorizado, ejecución de código de terceros, autenticación empresarial completa, Kubernetes, certificación de que una aplicación es segura, remediación automática y biometría real.

## Documentación

- [Visión del producto](docs/01_PRODUCTO_Y_REQUISITOS.md)
- [Arquitectura y contratos](docs/02_ARQUITECTURA_Y_CONTRATOS.md)
- [Roadmap académico](docs/03_ROADMAP_ACADEMICO.md)
- [Reglas permanentes para Codex](AGENTS.md)
- [Primer encargo para Codex](prompts/01_PRIMERA_ITERACION_CODEX.md)

## Preparar entorno virtual (cuando empiece la implementación)

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip --version
# Cuando Codex haya generado pyproject.toml:
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

### Linux / macOS

```bash
python3 -m venv .venv
./.venv/bin/python -m pip --version
# Cuando Codex haya generado pyproject.toml:
./.venv/bin/python -m pip install -e '.[dev]'
./.venv/bin/python -m pytest
```

No ejecutar `pip install` ni herramientas Python sin el prefijo del intérprete de `.venv`. No se necesita activar el entorno para usar sus binarios mediante rutas explícitas.

## Cómo comenzar

1. Poner estos archivos en la raíz del repositorio existente **sin sobrescribir contenido propio**. Revisar diferencias si ya existen archivos homónimos.
2. Abrir el directorio con Codex y usar `prompts/01_PRIMERA_ITERACION_CODEX.md` como primera tarea.
3. Exigir revisión de cambios y pruebas antes de avanzar.
4. Mantener un registro de decisiones en `docs/adr/` a medida que se implementa.
