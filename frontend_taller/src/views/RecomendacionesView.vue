<template>
  <div class="min-h-screen bg-surface">

    <!-- Header Fijo -->
    <header class="sticky top-0 z-50 w-full bg-white shadow-sm py-4 px-6 flex items-center justify-between">
      <button
        @click="goBack"
        class="w-10 h-10 flex items-center justify-center rounded-full bg-surface hover:bg-surface-dim text-on-surface transition"
      >
        ←
      </button>

      <h1 class="text-lg font-semibold text-on-surface">
        Recomendaciones – {{ cursoNombre }}
      </h1>

      <button
        @click="$router.push('/settings')"
        class="w-10 h-10 flex items-center justify-center rounded-full bg-surface-container text-primary hover:bg-surface-dim transition shadow-sm"
      >
        ⚙️
      </button>
    </header>

    <!-- Content -->
    <div class="max-w-4xl mx-auto px-6 py-10">

      <!-- Loading -->
      <div v-if="loading" class="flex flex-col items-center py-20 gap-4">
        <div class="w-12 h-12 border-4 border-gray-300 border-t-indigo-500 rounded-full animate-spin"></div>
        <p class="text-gray-600">Analizando perfiles...</p>
      </div>

      <!-- Sin recomendaciones -->
      <div v-else-if="!recommendations.length" class="text-center mt-20 text-outline">
        <h2 class="text-xl font-semibold mb-3">No hay recomendaciones</h2>
        <p>Revisa los datos procesados o selecciona otro curso.</p>
      </div>

      <!-- Lista -->
      <div v-else class="flex flex-col gap-6">

        <div
          v-for="(docente, index) in recommendationsSorted"
          :key="index"
          class="bg-white p-6 md:p-8 rounded-28px shadow-sm hover:shadow-md transition-shadow border border-transparent hover:border-surface-dim"
        >

          <!-- Top row -->
          <div class="flex items-center justify-between">

            <!-- Rank badge -->
            <div
              class="w-12 h-12 flex items-center justify-center rounded-full text-white font-semibold shadow"
              :class="rankColor(index)"
            >
              #{{ index + 1 }}
            </div>

            <div class="flex-1 px-6">
              <h3 class="text-lg font-semibold text-on-surface">
                {{ docente.nombre }}
              </h3>

              <p class="text-outline text-sm">{{ docente.email || 'Sin email' }}</p>
              <p class="text-primary text-sm font-medium mt-1">
                {{ docente.grado || "Sin grado académico" }}
              </p>
              <div class="mt-2 flex flex-wrap items-center gap-2">
                <span 
                  class="px-3 py-1 text-xs font-semibold rounded-full border"
                  :class="{
                    'bg-green-50 text-green-700 border-green-200': docente.confianza_etiqueta === 'Confianza Muy Alta',
                    'bg-blue-50 text-blue-700 border-blue-200': docente.confianza_etiqueta === 'Confianza Alta',
                    'bg-yellow-50 text-yellow-700 border-yellow-200': docente.confianza_etiqueta === 'Confianza Media',
                    'bg-red-50 text-red-700 border-red-200': docente.confianza_etiqueta === 'Confianza Baja'
                  }"
                >
                  {{ docente.confianza_etiqueta }}
                </span>
                <span class="px-3 py-1 bg-surface-container text-outline text-xs font-semibold rounded-full border border-surface-dim" title="Rendimiento respecto al primer puesto">
                  Match Relativo: {{ docente.score_relativo }}%
                </span>
              </div>
            </div>

            <!-- Botón de purga (Derecho al olvido) -->
            <button 
              @click="handleDelete(docente)" 
              class="mr-4 text-red-600 hover:text-white bg-red-50 hover:bg-red-600 px-4 py-2 rounded-full transition-colors text-xs font-semibold flex items-center gap-1 border border-red-100"
              title="Derecho al Olvido: Purgar perfil y vectores"
            >
              🗑️ Purgar
            </button>

            <!-- Score circle -->
            <div class="relative flex items-center justify-center">
              <div
                class="w-20 h-20 rounded-full flex items-center justify-center font-bold text-primary"
                :style="circleStyle(docente.score_combinado)"
              >
                <div class="absolute w-16 h-16 bg-white rounded-full flex items-center justify-center text-lg">
                  {{ Math.round(docente.score_combinado) }}%
                </div>
              </div>
            </div>

          </div>

          <!-- Divider -->
          <div class="w-full h-px bg-surface-container my-6"></div>

          <!-- XAI Intrínseca -->
          <div v-if="docente.xai_explanations" 
               class="mb-6 p-5 bg-surface rounded-2xl border border-surface-dim">
            <h4 class="text-sm font-bold text-on-surface mb-3">Auditoría del Emparejamiento</h4>
            <div class="text-sm text-outline whitespace-pre-wrap leading-relaxed">
              {{ docente.xai_explanations }}
            </div>
          </div>

          <!-- Detalles de Entidades (Extracción dura) -->
          <div class="space-y-3 text-sm mt-2">
            <div v-if="docente.evidencias?.entidades_clave?.length">
              <p class="font-medium text-outline mb-3">Tecnologías y conceptos en común con el sílabo:</p>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="e in docente.evidencias.entidades_clave"
                  :key="e"
                  class="px-4 py-1.5 rounded-lg bg-surface-container text-on-surface text-xs font-medium border border-surface-dim"
                >
                  {{ e }}
                </span>
              </div>
            </div>
          </div>

        </div>

      </div>

    </div>

  </div>
</template>

<script>
import { useAppStore } from "../store/app";
import { useRouter, useRoute } from "vue-router";
import { computed, onMounted, ref } from "vue";
import { deleteDocente } from "../services/api";

export default {
  name: "RecommendationsView",

  setup() {
    const store = useAppStore();
    const router = useRouter();
    const route = useRoute();
    const loading = ref(true);

    // Obtener el cursoId de la URL
    const cursoId = route.params.cursoId;

    const recommendationsSorted = computed(() =>
      [...store.recommendations].sort(
        (a, b) => b.score_combinado - a.score_combinado
      )
    );

    const rankColor = (index) => {
      if (index === 0) return "bg-yellow-500";
      if (index === 1) return "bg-gray-400";
      if (index === 2) return "bg-orange-500";
      return "bg-indigo-500";
    };

    const circleStyle = (score) => {
      const s = Math.min(Math.max(score, 0), 100);
      return {
        background: `conic-gradient(#6366f1 ${s}%, #e5e7eb ${s}%)`,
      };
    };

    // Cargar recomendaciones si no están ya
    onMounted(async () => {
      // Verificar si tenemos el curso en el store
      if (!store.currentCurso || store.currentCurso != cursoId) {
        // Intentar encontrar el curso
        const restored = store.restoreState();
        
        if (!restored || !store.hasData) {
          router.push('/ciclos');
          return;
        }
      }

      if (!store.recommendations?.length) {
        try {
          await store.fetchRecommendations();
        } catch (error) {
          console.error('Error cargando recomendaciones:', error);
        }
      }
      
      loading.value = false;
    });

    const goBack = () => {
      if (store.currentCiclo) {
        router.push(`/cursos/${store.currentCiclo}`);
      } else {
        router.push('/ciclos');
      }
    };

    const handleDelete = async (docente) => {
      const confirmed = confirm(
        `¿Estás seguro de que deseas PURGAR permanentemente los datos y vectores IA de ${docente.nombre}?\n\nEsta acción es irreversible y ejecutará el "Derecho al Olvido".`
      );
      if (!confirmed) return;

      try {
        await deleteDocente(docente.docente_id);
        // Filtrar del store localmente
        store.recommendations = store.recommendations.filter(r => r.docente_id !== docente.docente_id);
        store.saveState();
        alert("Datos y vectores del docente purgados correctamente del servidor.");
      } catch (error) {
        alert("Error al purgar los datos: " + error.message);
      }
    };

    return {
      cursoNombre: computed(() => store.currentCursoNombre),
      recommendations: computed(() => store.recommendations),
      recommendationsSorted,
      loading,
      rankColor,
      circleStyle,
      goBack,
      handleDelete,
      getSortedShapValues: (shapExplanations) => {
        if (!shapExplanations || typeof shapExplanations !== 'object') return {};
        
        // Convertir a array, ordenar por valor absoluto descendente, y reconvertir a objeto
        return Object.entries(shapExplanations)
          .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
          .slice(0, 5) // Mostrar solo los 5 factores más importantes
          .reduce((obj, [key, value]) => {
            obj[key] = value;
            return obj;
          }, {});
      },
      formatFeatureName: (feature) => {
        const names = {
          'area_match_count': 'Áreas',
          'lenguaje_match_count': 'Lenguajes',
          'herramienta_match_count': 'Herramientas',
          'metodologia_match_count': 'Metodologías',
          'contenido_match_count': 'Contenidos',
          'history_score': 'Historial',
          'semantic_score': 'Similitud Semántica'
        };
        return names[feature] || feature;
      }
    };
  },
};
</script>
