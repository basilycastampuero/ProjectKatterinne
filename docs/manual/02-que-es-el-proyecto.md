# 2. Qué es el proyecto

## 2.1 En una frase

**ProjectKatterinne es una compañera de IA que vive en tu ordenador, mira
qué estás haciendo, lo recuerda y, de vez en cuando, siente curiosidad y
te pregunta por ello.**

Todo ocurre en tu máquina: el modelo de lenguaje corre en tu GPU, los
recuerdos se guardan en un archivo local y nada sale a Internet.

## 2.2 Qué hace, en concreto

1. **Observa** qué aplicación y qué ventana tienes delante, preguntándoselo
   a Windows una vez por segundo.
2. **Interpreta** esa observación: "estás en VS Code, en el proyecto
   ProjectKatterinne, editando `engine.py`, y eso es programar".
3. **Recuerda** entre sesiones: en qué aplicaciones estuviste, cuánto rato,
   qué proyectos conoce y qué le has contado.
4. **Conversa** contigo por el terminal, sabiendo todo lo anterior.
5. **Decide si merece la pena hablar**. Casi siempre decide que no.
6. Cuando decide que sí, **redacta una pregunta** concreta sobre lo que
   haces: *"¿Qué estás implementando en questions.py?"*.
7. **Aprende de lo que le cuentas**: si le dices *"la memoria va con
   SQLite"*, lo recuerda, y en otra sesión lo sabrá.

## 2.3 Qué NO es

Esto es tan importante como lo anterior. El proyecto está diseñado para
**no** ser ninguna de estas cosas:

| No es… | Porque… |
|---|---|
| Un asistente que controla el PC | No hace clic, no escribe, no abre programas, no toca archivos. Solo **mira** |
| Un agente autónomo | No ejecuta acciones por su cuenta |
| Un vigilante de productividad | No mide si rindes, no te anima, no te riñe. No existen categorías como "productivo" o "distraído" |
| Un chatbot genérico con personalidad pegada | Su gracia está en saber qué haces y en callarse cuando no hay motivo para hablar |
| Un servicio en la nube | Nada de OpenAI, Anthropic ni Google. Todo local |

La idea central:

> La compañera no intenta controlarte. Intenta entender qué haces y, de vez
> en cuando, sentir curiosidad por ello.

Debería sentirse como **alguien sentado a tu lado que se interesa por lo
que haces**, no como un programa que te monitoriza.

## 2.4 Los principios

Casi todas las decisiones del código se explican con estos principios. Si
alguna vez algo te parece raro o innecesariamente complicado, vuelve aquí.

### Local primero

El funcionamiento básico no puede depender de ningún servicio externo. El
modelo corre en Ollama, en tu máquina. La memoria es un archivo SQLite en
`data/`. El único tráfico de red es a `127.0.0.1`, que es tu propio
ordenador.

### Privacidad primero

Todo lo que observa y recuerda se queda en tu equipo. Y dentro del equipo,
se protege también:

- Los **títulos de ventana nunca se escriben en el log**: pueden contener
  nombres de documentos, URLs o datos personales.
- Existe un **modo privacidad** que oculta todos los títulos, y una **lista
  negra** de aplicaciones (tu gestor de contraseñas, tu banco) de las que
  no se observa nada.
- Lo que dices y lo que recuerda **tampoco va al log**. Solo se registran
  cantidades: "se guardaron 2 hechos", nunca cuáles.

### Solo lectura

La compañera **observa, no actúa**. No hay ni una línea de código que haga
clic, escriba o ejecute comandos. La arquitectura deja la puerta abierta a
herramientas en el futuro, pero hoy no existen.

### Determinista antes que inteligente

Si algo se puede saber con certeza sin el modelo, **no se usa el modelo**.

```
❌  captura de pantalla → modelo → "parece que está en VS Code"
✅  Windows → "la ventana activa es de Code.exe" → VS Code
```

Windows *sabe* qué ventana tiene el foco. Preguntárselo a un modelo sería
lento, caro y, además, el modelo podría equivocarse. Por eso hay tanto
código "aburrido": tablas de procesos, análisis de títulos, expresiones
regulares. **El modelo se usa solo para lenguaje**: conversar, redactar
preguntas y proponer qué recordar.

### Cada dato lleva de dónde salió

No es lo mismo:

- **Observado**: el proceso activo *es* `Code.exe`. Windows lo dice.
- **Inferido**: el proyecto *probablemente* se llama ProjectKatterinne,
  porque lo pone el título de la ventana. Puede estar mal.
- **Confirmado**: *la persona dijo* que trabaja en ProjectKatterinne.

Si el sistema guardara lo inferido como si fuera cierto, en dos semanas la
memoria estaría llena de cosas que se inventó él mismo, sin forma de
distinguirlas. Por eso **cada dato viaja con su procedencia** (el tipo
`Signal` del capítulo 5) y llega así hasta el modelo, que puede decir "creo
que estás en X, ¿es así?" en vez de afirmarlo.

### El silencio es la salida normal

Una buena sesión de dos horas puede tener 47 cambios de ventana y **una**
pregunta. Eso es mejor que 47 preguntas. El motor de curiosidad está
construido para **callarse por defecto**: hay diez formas distintas de
decidir no hablar y solo siete tipos de pregunta.

### Al modelo no se le cree: se le valida

Cuando el modelo le dice algo **al sistema** (una pregunta que hacer, un
recuerdo que guardar), la respuesta pasa por un validador que comprueba que
no se ha inventado nada. Si no pasa, se descarta. Una pregunta mala o un
recuerdo falso hacen mucho más daño que ninguno.

### Lo más pequeño que funcione

No se construye infraestructura para necesidades hipotéticas. Cada
dependencia tiene que justificarse (por eso hay **cero** dependencias de
ejecución). Antes de añadir algo complicado, se mide si hace falta.

## 2.5 El equipo objetivo

El proyecto está pensado para un portátil concreto, y eso condiciona
decisiones reales:

| | |
|---|---|
| CPU | AMD Ryzen 7 7745HX |
| GPU | NVIDIA RTX 4070 Laptop, **8 GB de VRAM** |
| RAM | 32 GB |
| Sistema | Windows 11 |

Los 8 GB de VRAM son el límite duro: el modelo tiene que caber entero. De
ahí sale que se probaran solo modelos de 4 a 9 mil millones de parámetros
cuantizados a 4 bits, y que ganara `qwen3.5:9b` (6,67 GB cargado) por
benchmark ([ADR-012](../architecture-decisions/ADR-012-qwen3.5-9b-chosen-by-benchmark.md)).
De ahí sale también que la aplicación sea ligera cuando solo observa:
`--watch` no carga el modelo.

## 2.6 Las fases

El proyecto se construye por fases, cada una sobre la anterior. Nunca se
implementan varias a la vez.

| Fase | Qué añade | Estado |
|---|---|---|
| 0 | Esqueleto: estructura, configuración, logs, tests | ✅ |
| 1 | Conversar con un modelo local por terminal | ✅ |
| 2 | Saber qué ventana está activa | ✅ |
| 3 | Convertir la ventana en contexto con significado | ✅ |
| 4 | Memoria persistente en SQLite | ✅ |
| 5 | Visión: capturas de pantalla y modelo multimodal | pendiente |
| 6 | Decidir cuándo merece la pena hablar | ✅ |
| 7 | Redactar preguntas a partir del contexto | ✅ |
| — | Aprender hechos de la conversación | ✅ |
| 8 | Voz: hablar y escuchar en local | pendiente |
| 9 | Memoria avanzada: consolidación, búsqueda semántica | pendiente |
| 10 | Interfaz de escritorio y avatar | pendiente |

Con las fases 0 a 4, 6 y 7 está completo el **MVP** (la versión mínima que
demuestra la idea). Lo pendiente, con su contexto y prioridad, está en
[`docs/PENDIENTE.md`](../PENDIENTE.md).

## 2.7 Las decisiones importantes (ADR)

Cada una tiene su documento en `docs/architecture-decisions/`. Léelos
cuando toques la parte correspondiente:

| ADR | Decisión | En pocas palabras |
|---|---|---|
| 001 | Usar Ollama | Es el runtime local más sencillo; está detrás de una interfaz por si hay que cambiarlo |
| 002 | Cero dependencias de ejecución | La biblioteca estándar basta, y un programa que lee tus ventanas no debe tener código de terceros que auditar |
| 003 | Desactivar el modo de razonamiento | Costaba 5 segundos y 300 tokens decir "¡Hola!" |
| 004 | `ctypes` en vez de `pywin32` | Seis funciones de Windows no justifican una dependencia |
| 005 | La privacidad es una capa que envuelve | Es imposible obtener una ventana sin pasar por el filtro |
| 006 | Procedencia en vez de valores sueltos | Distinguir observado, inferido y confirmado |
| 007 | La memoria llega al prompt | Si el modelo no recibe los recuerdos, no sirven de nada |
| 008 | El silencio por construcción | Barreras que solo pueden decir que no, en orden |
| 009 | Validar lo que dice el modelo | JSON válido no es JSON correcto |
| 010 | Un recuerdo necesita una cita literal | Solo se recuerda lo que la persona dijo de verdad |
| 011 | Preguntar por un título no es verlo | Se interesa por la página en la que te quedas, nunca por las sensibles, y sin guardar qué páginas visitas |

---

**Anterior:** [1. Conceptos previos](01-conceptos-previos.md) ·
**Siguiente:** [3. Instalar y ejecutar](03-instalar-y-ejecutar.md)
