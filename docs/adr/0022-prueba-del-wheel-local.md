# ADR 0022 — Comprobar el wheel en un entorno de consumo local

Decisión del 23 de noviembre de 2026.

## Contexto

Las pruebas del proyecto cargan el código desde el checkout. Una instalación
editable también puede mostrar una página o cargar un corpus aunque el wheel
haya omitido ese recurso. Además, el módulo importado anunciaba una versión
diferente de la declarada para la distribución.

## Decisión

La versión de ejecución se comparte con OpenAPI y se contrasta por prueba con
la versión estática de `pyproject.toml`. Se conserva este dato estático para
las herramientas que leen los metadatos del proyecto antes de construirlo.

La comprobación de distribución es un comando de desarrollo independiente.
Usa pip y el backend del proyecto sobre una copia temporal de archivos seguidos
por Git. Instala el resultado en un entorno nuevo bajo `.local/`. Por defecto
resuelve dependencias desde `.local/wheels/`. El operador puede autorizar
PyPI para una ejecución.

Se comprueba la huella del archivo instalado, la procedencia de la importación,
el contenido del paquete, la versión de OpenAPI y el funcionamiento de ambos
corpus a través de la CLI instalada. El recibo solo se emite tras completar la
secuencia.

## Consecuencias

La comprobación ordinaria de código conserva su uso diario sin instalaciones.
La de distribución tiene un costo adicional de disco y tiempo durante la
construcción. El resultado identifica los bytes de un wheel y una instalación
concreta. La reproducibilidad entre máquinas requiere fijar y comparar también
las versiones de las dependencias.

El [procedimiento de comprobación](../27_VALIDACION_DEL_PAQUETE.md) detalla
los comandos y la evidencia que produce cada uno.
