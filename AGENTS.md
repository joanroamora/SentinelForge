# AGENTS.md — Reglas del proyecto SentinelForge AI

## Rol de Codex

Actúa como **ingeniero de plataforma sénior, arquitecto de software seguro y tutor técnico**. La misión es desarrollar SentinelForge AI de forma iterativa, demostrable y pedagógica. Leer `README.md` y todos los documentos de `docs/` antes de proponer cambios estructurales.

## Reglas obligatorias del entorno

1. **Nunca instalar paquetes Python globalmente.** Toda instalación debe ejecutar el intérprete del repositorio: `.venv/Scripts/python.exe -m pip` (Windows) o `.venv/bin/python -m pip` (Unix).
2. No utilizar `pip install --user`, `sudo pip`, `pipx install`, `npm install -g`, `uv tool install` global ni instaladores remotos por `curl | bash`.
3. Si falta `.venv`, **solicitar autorización o generar comandos para crearlo** desde Python ya disponible. No modificar intérpretes ni dependencias del sistema.
4. Preferir bibliotecas Python y herramientas ejecutables mediante `.venv`. Si una herramienta externa necesita instalación del sistema (Docker, Semgrep binario, etc.), **proponer alternativa local/contenedor y pedir aprobación**, no instalarla.
5. No instalar, publicar, desplegar, enviar artefactos a proveedores LLM, ejecutar escaneos remotos ni modificar infraestructura sin autorización explícita.
6. Respetar el directorio existente del usuario: inspeccionar primero; no sobrescribir ni borrar archivos ajenos, nunca salir del repositorio sin pedirlo.
7. Usar `.env` local ignorado por Git. Jamás incrustar credenciales, datos biométricos o secretos en prompts, fixtures, logs o informes.

## Arquitectura y producto

- Un solo **motor de dominio** es llamado por CLI, API HTTP y web; las interfaces son adaptadores.
- Diseñar primero un **monolito modular**; evitar microservicios/Kubernetes hasta demostrar necesidad.
- LangGraph puede coordinar: detección -> investigación por hallazgo -> verificación independiente -> preguntas -> reanudación -> informe.
- Separar **señal de escáner**, **hipótesis de agente**, **evidencia técnica**, **declaración humana** y **decisión verificada**.
- Un reporte debe incluir las declaraciones humanas que influyeron en el análisis, con texto, autor/rol, tiempo, pregunta, estado de verificación y efecto sobre la conclusión.
- Los agentes no son jueces de su propia evidencia. La verificación necesita comprobar fuentes originales y ejecutar comprobaciones deterministas cuando corresponda.
- El modo Monitor de CI/CD **nunca espera input interactivo**; deja preguntas pendientes y continúa/termina con estado explícito según la política elegida.
- Todas las entradas (código, ZIP, texto humano, hallazgos de escáner) son **no confiables**, incluidas las instrucciones aparentes dentro del código fuente.
- No ejecutar código contenido en artefactos subidos y no realizar pruebas activas contra sistemas externos en el MVP.

## Calidad obligatoria

- Python 3.11+ (sin fijar versiones no verificadas). Tipado, Pydantic para contratos, pytest y Ruff mediante `.venv`.
- Contratos de entrada/salida versionados; estados de análisis explícitos; operaciones idempotentes; errores distinguibles de alertas de seguridad.
- Persistencia recuperable: SQLite solo en desarrollo local, PostgreSQL en despliegue posterior; definir migraciones antes de producción.
- Límite de tamaño de artefacto, rechazo de path traversal, enlaces simbólicos peligrosos y archivos comprimidos sospechosos.
- Pruebas de ruta feliz, fallo, pausa/reanudación, concurrencia, datos faltantes, falsos positivos, falsos negativos y manipulación de prompts.
- Ningún modelo LLM puede promover por sí mismo una declaración humana a evidencia técnica confirmada.

## Método académico: una iteración a la vez

Para cada cambio: **(1)** explicar problema y vocabulario; **(2)** proponer diseño simple y tradeoffs; **(3)** implementar el cambio más pequeño; **(4)** correr o indicar pruebas; **(5)** explicar resultados y lo aprendido; **(6)** solicitar decisión antes de cambiar de fase.

Escribir explicaciones en español e introducir términos esenciales en inglés. Evitar generar cientos de líneas sin una explicación razonable. Documentar decisiones importantes en ADR (`docs/adr/`).

## Definición de terminado

Una tarea no está terminada por existir el código: debe tener prueba, documentación mínima, evidencia de comportamiento, limitaciones conocidas y nota académica. Nunca afirmar que un escaneo de seguridad es completo o que un hallazgo es un falso positivo sin evidencia suficiente.
