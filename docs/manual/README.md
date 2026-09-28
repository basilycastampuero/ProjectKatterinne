# Manual del proyecto

Este manual es para quien llega a ProjectKatterinne **sin experiencia
previa** en un proyecto así. No da nada por sabido: explica qué es cada
pieza, por qué está hecha como está, cómo viajan los datos y cómo se
trabaja en el repositorio día a día.

Si ya conoces el proyecto y buscas algo concreto, la referencia rápida es
[`docs/GUIA.md`](../GUIA.md). Este manual va antes que ella.

## Cómo leerlo

Los capítulos están pensados para leerse en orden la primera vez. Cada uno
se apoya en los anteriores.

| # | Capítulo | Qué vas a entender | Tiempo |
|---|---|---|---|
| 1 | [Conceptos previos](01-conceptos-previos.md) | Lo que tienes que saber antes de abrir el código: modelos de lenguaje, Ollama, SQLite, dataclasses, interfaces… | 40 min |
| 2 | [Qué es el proyecto](02-que-es-el-proyecto.md) | Para qué existe, qué **no** es y los principios que explican casi todas las decisiones | 20 min |
| 3 | [Instalar y ejecutar](03-instalar-y-ejecutar.md) | Ponerlo en marcha, los modos de ejecución, los comandos, la configuración y los logs | 30 min |
| 4 | [La arquitectura](04-arquitectura.md) | Las capas, quién puede hablar con quién y por qué | 30 min |
| 5 | [Las estructuras de datos](05-estructuras-de-datos.md) | Cada tipo importante, campo a campo, con ejemplos | 45 min |
| 6 | [Los flujos del programa](06-flujos.md) | Qué pasa, paso a paso, desde que arranca hasta que se cierra | 45 min |
| 7 | [Archivo por archivo](07-archivo-por-archivo.md) | Todos los archivos del repositorio: qué hacen y por qué existen | consulta |
| 8 | [Los tests](08-tests.md) | Cómo se prueba sin GPU ni Windows, y cómo escribir tu primer test | 30 min |
| 9 | [Cómo se trabaja aquí](09-como-se-trabaja.md) | Ramas, commits, convenciones, documentación y un primer cambio guiado | 30 min |
| 10 | [Glosario y preguntas frecuentes](10-glosario-y-faq.md) | Las palabras del proyecto y las dudas que siempre salen | consulta |

## Un consejo antes de empezar

Lee con el código abierto al lado. Cada vez que el manual nombre un
archivo, ábrelo y busca lo que se describe. Los comentarios del código
explican **por qué** está hecho así; este manual explica **cómo encaja todo**.
Las dos cosas juntas son las que dan el cuadro completo.

Y ejecuta la aplicación pronto. `--watch` no necesita ni el modelo ni la
GPU, y ver el contexto cambiar mientras cambias de ventana enseña más que
cualquier diagrama.
