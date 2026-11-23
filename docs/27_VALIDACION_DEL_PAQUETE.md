# Probar el paquete que recibe otra persona

Un *wheel* es el archivo `.whl` que instala Python. La copia de desarrollo puede
encontrar módulos y recursos directamente en `src/`. Por eso, que la web abra en
desarrollo dice poco sobre si el HTML, los estilos y los datos viajarán dentro
del archivo que se entregue.

Al preparar esta prueba descubrimos que el módulo de Python anunciaba 0.1.0,
mientras que la distribución declarada y la API anunciaban 0.2.0. El módulo y
la API comparten ahora la versión de ejecución. Una prueba comprueba que ambos
coinciden con la versión declarada en `pyproject.toml`.

## Comprobar una instalación

El comando parte de la raíz del repositorio y requiere la `.venv` existente y
Git. Su ejecución construye e instala paquetes temporales y requiere autorización
del operador. En Windows, con las dependencias ya disponibles como wheels en
`.local/wheels/`, se puede trabajar completamente sin conexión.

```powershell
.\.venv\Scripts\python.exe -m scripts.validate_wheel
```

En Linux y macOS se usa `./.venv/bin/python -m scripts.validate_wheel`. La
carpeta debe contener los wheels de construcción y los de ejecución, incluidas
sus dependencias transitivas, compatibles con el Python y la plataforma que
se prueban. Una carpeta vacía devuelve `wheelhouse_empty` antes de instalar.

Si el operador autoriza descargas desde PyPI, la misma prueba acepta una opción
explícita para esa ejecución.

```powershell
.\.venv\Scripts\python.exe -m scripts.validate_wheel --allow-pypi
```

1. El comando copia el contenido de trabajo de los archivos que Git sigue a una
   carpeta nueva bajo `.local/`. Conviene añadir a Git los módulos y recursos
   nuevos que deban formar parte de la distribución. La copia evita incorporar
   resultados de compilaciones anteriores o alterar los metadatos editables.
2. El intérprete de `.venv` pide a pip construir el wheel con el backend
   declarado en `pyproject.toml`. Crea un segundo entorno temporal, vacío, y
   dirige a ese entorno la instalación del archivo y sus dependencias. Después
   ejecuta `pip check`. Cachés de pip desactivadas y temporales dentro de
   `.local/` mantienen la operación acotada al proyecto.
3. El segundo intérprete arranca en modo aislado. Comprueba el origen de la
   importación, la huella SHA-256 que registró pip para el wheel local y los
   archivos del paquete frente a las fuentes de este checkout. También compara
   la versión de la distribución instalada, la del módulo importado, la
   declarada en el proyecto y la publicada por OpenAPI.
4. Desde una carpeta vacía, el comando de terminal instalado evalúa `baseline`
   y `challenge`. Se leen ambos informes y se comprueban su estado, identidad
   del motor y lista de casos. Esto ejercita los procesos auxiliares y los datos
   instalados que necesita el análisis. Solo se usan los ejemplos sintéticos del
   producto.

## Leer el resultado

Cada ejecución que inicia la construcción crea una carpeta nueva en
`.local/packaging/`. Allí quedan el wheel si llegó a construirse y los logs de
los pasos ejecutados. El código 0 y `receipt.json` corresponden a la comparación
final aprobada. El recibo identifica el archivo y su SHA-256, la versión probada,
el Python, la cantidad de archivos comprobados, los casos por corpus y el origen
de las dependencias. Un fallo devuelve 2. El entorno temporal se retira al salir.

La prueba habitual de código sigue siendo `scripts/validate_local.py`. Su
manifiesto identifica también los scripts de comprobación en la huella de
fuentes. La evidencia de una instalación limpia se consulta por separado en
el recibo del wheel.

## Evidencia de la preparación del 23 de noviembre de 2026

En Windows con Python 3.14.10 de la `.venv`, la validación del checkout registró
**868 pruebas aprobadas, 2 omitidas y Ruff limpio**. Los 23 casos nuevos cubren
el protocolo de empaquetado. Las dos evaluaciones habituales completaron sus 28
y 20 casos. La huella de fuentes coincidió al inicio y al final. El manifiesto
quedó en `.local/validation/20261123T230516Z-ff682f83/manifest.json`.

Una preparación con Git reprodujo en la copia temporal los 31 archivos seguidos
del paquete, con idéntico contenido. El módulo importado y el esquema OpenAPI
devolvieron 0.2.0. Los metadatos editables de la instalación de desarrollo
anterior seguían registrando 0.1.0. La caché local de wheels estaba vacía y
esta ejecución comprobó el código con las dependencias existentes. Quedó
pendiente construir e instalar un wheel real para obtener su recibo.

## Alcance y nota académica

El comprobador admite la distribución de SentinelForge construida desde este
repositorio. La comparación incluye los módulos Python, los datos JSON y los
recursos HTML, CSS y JavaScript del paquete. La generación del esquema OpenAPI
carga la aplicación y su portada. La navegación en un navegador, la resolución
idéntica de dependencias en otras fechas y la publicación son hitos distintos.
Cada recibo corresponde al sistema y al Python elegidos para esa ejecución.

Las pruebas de regresión comprueban diferencias de versión, contenido ausente
o cambiado, metadatos editables, índices de paquetes heredados, errores de
instalación y recibos cuya huella corresponde a otro archivo. Los ensayos del
protocolo sustituyen la instalación por respuestas controladas. La verificación
de una distribución real requiere ejecutar el comando sobre una construcción
del proyecto.

Preguntas de repaso

- ¿Cómo podría funcionar una página en desarrollo y faltar su CSS al instalar?
- ¿Qué dos lugares se consultan para vincular el wheel con la instalación?
- ¿Qué permite concluir el resultado si ambos corpus pasan en un solo Windows?

La [decisión de empaquetado](adr/0022-prueba-del-wheel-local.md) describe la
separación entre pruebas del código y de la distribución.
