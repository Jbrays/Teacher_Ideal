# Manual de Usuario: Sistema Inteligente de Asignación Docente

## 1. Introducción
Bienvenido al Sistema de Asignación Docente. Esta plataforma utiliza Inteligencia Artificial para asistir a los directores de escuela y gestores académicos en la selección de los docentes más idóneos para cada asignatura, basándose en el análisis semántico de sílabos, currículums y el historial de dictado.

---

## 2. Acceso al Sistema
1.  Ingrese a la dirección web de la plataforma.
2.  Haga clic en el botón **"Iniciar Sesión con Google"**.
3.  Seleccione su cuenta institucional o autorizada.
4.  Una vez autenticado, será redirigido al **Panel Principal (Dashboard)**.

---

## 3. Configuración Inicial (Primer Uso)
Antes de generar recomendaciones, es necesario conectar el sistema con los documentos de la institución.

1.  Diríjase al menú lateral y seleccione **"Configuración"**.
2.  En la sección **"Conexión con Google Drive"**, haga clic en **"Vincular Cuenta"**.
3.  Autorice los permisos de lectura para que el sistema pueda acceder a los archivos.
4.  **Selección de Carpetas:**
    *   **Carpetas de CVs:** Seleccione la carpeta que contiene los currículums (PDF) de los docentes.
    *   **Carpetas de Sílabos:** Seleccione la carpeta raíz que contiene los sílabos (Word/PDF) organizados por ciclos.
    *   **Carpetas de Horarios:** Seleccione la carpeta con los horarios históricos (PDF) para analizar la experiencia previa.

---

## 4. Procesamiento de Datos
El sistema permite procesar la información de manera independiente para mayor control. En la vista de **Configuración**:

### A. Procesar CVs
*   Haga clic en **"Procesar solo CVs"**.
*   El sistema leerá cada PDF, extraerá la información del docente y detectará sus habilidades técnicas (ej. "Python", "Scrum") usando Inteligencia Artificial.
*   *Tiempo estimado: 10-30 segundos por CV.*

### B. Procesar Sílabos
*   Haga clic en **"Procesar solo Sílabos"**.
*   El sistema analizará el contenido de cada curso para entender qué temas se enseñan.
*   *Nota:* Si un sílabo ya fue procesado anteriormente, el sistema lo omitirá para ahorrar tiempo.

### C. Procesar Horarios
*   Haga clic en **"Procesar solo Horarios"**.
*   El sistema extraerá el historial de qué docente dictó qué curso y en qué periodo, para construir la base de experiencia.

> **Importante:** Puede ver el progreso en tiempo real en la barra de estado. Si ocurre un error (ej. internet inestable), puede reintentar el proceso específico sin perder lo avanzado.

---

## 5. Generación de Recomendaciones
Esta es la función principal del sistema.

1.  Vaya al menú **"Cursos"** o **"Recomendaciones"**.
2.  Seleccione el **Ciclo** y luego el **Curso** específico que desea asignar (ej. "Inteligencia Artificial").
3.  El sistema mostrará una lista de docentes ordenados por un **Puntaje de Compatibilidad (Score)**.

### ¿Cómo interpretar el Ranking?
El puntaje (0 a 100%) se calcula combinando tres factores:
*   **Afinidad Semántica:** ¿Qué tanto se parece el CV del docente al contenido del sílabo? (Análisis profundo de texto).
*   **Historial:** ¿Ha dictado este curso antes?
*   **Grado Académico:** ¿Cumple con el grado requerido (Magíster/Doctor)?

### Explicabilidad (¿Por qué este docente?)
Para entender la recomendación, haga clic en la tarjeta del docente:
*   Verá un gráfico de **"Explicación de la IA"**.
*   El sistema le dirá en lenguaje natural: *"Este docente es recomendado principalmente por su alta coincidencia en herramientas (Python, TensorFlow) y porque dictó el curso en el 2023-10."*

---

## 6. Preguntas Frecuentes

**¿Qué hago si no aparecen docentes?**
Verifique que haya procesado correctamente los CVs en la sección de Configuración.

**¿El sistema decide por mí?**
No. El sistema es una herramienta de **apoyo a la decisión**. Le presenta los mejores candidatos con evidencia, pero la asignación final es responsabilidad del gestor académico.

**¿Cómo actualizo los datos para un nuevo semestre?**
Simplemente suba los nuevos sílabos o CVs a las carpetas de Drive y vuelva a ejecutar el procesamiento correspondiente.
