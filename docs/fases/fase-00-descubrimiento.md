# Fase 0 — Descubrimiento y definición del producto

> **Proyecto:** Editor de Clips Virales
> **Fase:** 0 de 10
> **Estado:** cerrada (pendiente de aprobación del usuario)
> **Fecha de inicio:** 2026-11-09
> **Fecha de cierre:** 2026-11-09
> **Documento base:** `SKILLS.md` (SkillNeitor 1.2.0, 23 ítems, 12 categorías)

---

## 1. Resumen ejecutivo

El Editor de Clips Virales es una herramienta **local-first** que recibe la transcripción
de un video (JSON con marcas de tiempo) y devuelve un conjunto de clips candidatos con:

- marcas de inicio y fin,
- un **gancho** de menos de 10 palabras,
- **subtítulos dinámicos** de 4–5 palabras por línea con palabras clave resaltadas,
- título, descripción y **hashtags** adaptados a TikTok/Reels o YouTube Shorts.

La aplicación **no renderiza ni corta video**. Su salida son metadatos y textos que otro
proceso (o el editor del usuario) usa para producir el clip final.

---

## 2. Planeación

### 2.1 Objetivo de la fase

Dejar explícito, antes de elegir tecnología, **qué problema resuelve el producto, para
quién y por qué merece existir**, con una propuesta de valor contrastable y al menos una
hipótesis falsable con métrica asociada.

### 2.2 Problema (sin nombrar la solución)

> Un creador que publica video corto debe revisar manualmente transcripciones largas para
> decidir qué fragmentos tienen más probabilidad de retener audiencia; el proceso consume
> tiempo, depende de la intuición y suele producir clips sin un gancho claro ni subtítulos
> optimizados para lectura rápida.

El problema se formula como **hipótesis verificable**: si el creador no logra identificar
rápido los momentos de mayor interés, entonces publica menos clips o de menor calidad, y
pierde alcance potencial.

### 2.3 Usuarios

| Tipo | Perfil | Necesidad principal | Contexto de uso |
|---|---|---|---|
| **Primario** | Creador de contenido individual (1–5 videos/semana) | Encontrar los mejores momentos y publicar rápido | Escritorio, después de grabar y transcribir, antes de publicar |
| **Secundario** | Marketer / community manager | Producir clips consistentes para varias marcas | Escritorio, flujo por lotes |
| **Secundario** | Emprendedor / experto que vende con contenido | Convertir una charla larga en piezas cortas | Escritorio, una vez por semana |

**Contexto de uso:** el usuario ya tiene la transcripción (generada por Whisper u otra
herramienta) y quiere pasar de “texto largo” a “clips listos para publicar” sin subir el
video ni la transcripción a la nube.

### 2.4 Alternativas actuales y coste de no resolverlo

| Alternativa | Limitación |
|---|---|
| Revisar la transcripción a mano | 30–90 min por video; sesgo de intuición; se omiten buenos momentos |
| Herramientas de recorte automático | Suelen exigir subir el video; poca explicabilidad; subtítulos rígidos |
| Pedir clips a un LLM en un chat manual | Sin timestamps verificables, sin formato estable, sin historial |
| No hacer clips | Se pierde alcance en TikTok, Reels y Shorts |

**Coste de no resolverlo:** horas de edición por video, menor frecuencia de publicación y
clips que no aprovechan los momentos de mayor retención.

### 2.5 Propuesta de valor

> Convierte una transcripción en un set de clips listos para publicar —gancho, subtítulos
> dinámicos y hashtags— en minutos, con un criterio de retención explicable y sin subir el
> video a la nube.

Atributos diferenciales:

1. **Local-first:** Ollama y SQLite en el equipo; la transcripción no sale del dispositivo.
2. **Explicable:** cada clip incluye puntuación y motivo (`reason`), no solo el resultado.
3. **Degradación clara:** si Ollama no está disponible, el motor heurístico sigue funcionando.
4. **Formato estable:** salida JSON validada y exportable (JSON, SRT, VTT).
5. **Accesible:** interfaz navegable con teclado, contraste AA y movimiento reducido.

### 2.6 Hipótesis falsables y métricas

| ID | Hipótesis | Métrica | Umbral de validación |
|---|---|---|---|
| **H1** | Un creador tarda menos en elegir un clip con la app que revisando la transcripción a mano. | Tiempo hasta exportar el primer clip | ≥ 50 % menos que la línea base manual |
| **H2** | Los ganchos generados cumplen las reglas de retención (≤ 10 palabras, curiosidad/urgencia). | % de ganchos que pasan validación automática | ≥ 95 % |
| **H3** | Los subtítulos respetan el límite de lectura rápida. | % de líneas con ≤ 5 palabras | 100 % |
| **H4** | El usuario publica o exporta al menos un clip sugerido por sesión. | Tasa de exportación por sesión | ≥ 40 % en pruebas con 5 usuarios |

> Las hipótesis H1 y H4 requieren validación con usuarios reales. El MVP técnico entrega
> la instrumentación y los criterios para medirlas.

### 2.7 Métricas de éxito del producto

- **North Star:** % de clips sugeridos que el usuario exporta o publica.
- **Secundarias:**
  - tiempo hasta el primer clip,
  - % de ganchos aceptados sin edición,
  - % de líneas de subtítulo dentro del límite,
  - sesiones con análisis completado sin error,
  - satisfacción declarada (1–5) al finalizar.

### 2.8 Alcance

#### Sí incluye

- Análisis semántico de la transcripción para detectar picos de interés (historias, datos
  impactantes, opiniones polémicas, consejos prácticos).
- Redacción de ganchos para los primeros 3 segundos del clip.
- Formateo de subtítulos dinámicos (resaltado de palabras clave, división para lectura rápida).
- Sugerencia de títulos, descripciones y hashtags por plataforma.
- Salida JSON estructurada y exportación SRT/VTT.

#### No incluye

- Renderizado, corte o procesamiento de video real.
- Generación de voz en off (TTS) o avatares.
- Análisis visual de imágenes (solo audio/transcripción).
- Publicación automática en redes sociales.
- Entrenamiento de modelos propios.

### 2.9 Decisiones aprobadas por el usuario (2026-11-09)

| Decisión | Opción elegida | Consecuencia |
|---|---|---|
| Stack / formato | **Python + web** (FastAPI + SQLite + frontend web) | Backend Python, UI web accesible sin build; empaquetado de escritorio en fase posterior |
| Motor de IA | **Ollama + heurísticas** | LLM local opcional; fallback determinista si Ollama falla |
| Persistencia | **SQLite local, 1 usuario** | Historial de análisis y clips; sin login |
| Entrada | **Formato estándar flexible** (Whisper: segmentos y/o palabras) | Parser tolerante y validado |
| Idioma | **Español** | UI, docs, errores y changelog en español |
| Plan | **11 fases (0–10)** | Ejecución secuencial con aprobación al cierre de cada fase |

### 2.10 Restricciones y supuestos

- El usuario dispone de una transcripción JSON; la app no transcribe audio en el MVP.
- Ollama es opcional: la app debe funcionar sin él y explicar cómo instalarlo.
- El equipo de destino es Windows/macOS/Linux con Python 3.11+.
- El MVP es de un solo usuario; no hay cuentas ni sincronización.
- No se procesan binarios de video: solo texto y timestamps.

### 2.11 Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Ollama no instalado o caído | Media | Alto | Fallback heurístico + mensaje con instrucciones |
| Transcripción con timestamps inconsistentes | Media | Alto | Validación, normalización y advertencias |
| Alucinaciones del LLM (timestamps o citas inventadas) | Media | Alto | El LLM solo puntúa/redacta; los timestamps salen del parser |
| Transcripciones muy largas | Media | Medio | Límite de tamaño, chunking y presupuesto de tiempo |
| Fuga de datos a la nube | Baja | Alto | Todo local por defecto; sin telemetría externa |
| Subtítulos ilegibles | Media | Medio | Regla dura de 4–5 palabras y pruebas automáticas |
| Baja calidad de los clips | Media | Alto | Evaluación con casos de oro y revisión humana |

### 2.12 Criterios de aceptación de la fase

Tomados de la skill **“Definición del problema y propuesta de valor”**:

- [x] Existe un documento de una página con problema, usuarios y valor.
- [x] El equipo puede explicar el problema sin mencionar la implementación.
- [x] Hay al menos una hipótesis falsable y una métrica asociada.

Criterios adicionales de esta fase:

- [x] Alcance “sí incluye / no incluye” explícito.
- [x] Decisiones de stack, IA, persistencia, entrada e idioma registradas.
- [x] Riesgos principales con mitigación.
- [x] Métricas de éxito y North Star definidas.

### 2.13 Actividades realizadas

1. Lectura completa de `SKILLS.md` (23 ítems, 12 categorías).
2. Extracción del alcance funcional y de las restricciones del producto.
3. Formulación del problema sin nombrar la solución.
4. Identificación de usuarios primario/secundarios y contexto de uso.
5. Definición de propuesta de valor, hipótesis y métricas.
6. Registro de las decisiones aprobadas por el usuario.
7. Análisis de riesgos y criterios de aceptación.

### 2.14 Evidencia

- Este documento: `docs/fases/fase-00-descubrimiento.md`.
- Respuestas del usuario registradas en la sección 2.9.
- `SKILLS.md` como fuente de alcance y criterios.

---

## 3. Cierre de fase

### 3.1 Resultado

La fase queda **cerrada**: el problema, los usuarios, la propuesta de valor, el alcance,
las métricas y los riesgos están documentados y son verificables. No se escribió código
de producto en esta fase.

### 3.2 Qué queda fuera (deuda consciente)

- Validación de H1 y H4 con usuarios reales: se hará después del MVP funcional.
- Investigación de mercado formal: fuera del alcance de este proyecto técnico.

### 3.3 Handoff a la Fase 1

La Fase 1 tomará estas decisiones como entrada para producir:

- arquitectura de componentes,
- ADRs (stack, persistencia, LLM, SSE, frontend),
- contratos de entrada/salida,
- borrador de API OpenAPI,
- estrategia de pruebas y observabilidad.

### 3.4 Criterio de aprobación para continuar

El usuario aprueba este cierre y autoriza el inicio de la **Fase 1 — Arquitectura,
stack y contratos**.
