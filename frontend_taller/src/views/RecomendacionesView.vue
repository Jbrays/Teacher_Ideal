<template>
  <div class="min-h-screen bg-gray-100">

    <!-- Header Fijo -->
    <header class="sticky top-0 z-50 w-full bg-white shadow-sm py-4 px-6 flex items-center justify-between">
      <button
        @click="goBack"
        class="text-gray-600 hover:text-indigo-500 transition text-xl"
      >
        ←
      </button>

      <h1 class="text-lg font-semibold text-gray-800">
        Recomendaciones – {{ cursoNombre }}
      </h1>

      <button
        @click="$router.push('/settings')"
        class="text-gray-600 hover:text-indigo-500 transition text-xl"
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
      <div v-else-if="!recommendations.length" class="text-center mt-20 text-gray-600">
        <h2 class="text-xl font-semibold mb-3">No hay recomendaciones</h2>
        <p>Revisa los datos procesados o selecciona otro curso.</p>
      </div>

      <!-- Lista -->
      <div v-else class="flex flex-col gap-6">

        <div
          v-for="(docente, index) in recommendationsSorted"
          :key="index"
          class="bg-white p-6 rounded-2xl shadow hover:shadow-xl transition border border-transparent hover:border-indigo-400"
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
              <h3 class="text-lg font-semibold text-gray-800">
                {{ docente.nombre }}
              </h3>

              <p class="text-gray-500 text-sm">{{ docente.email || 'Sin email' }}</p>
              <p class="text-indigo-500 text-sm font-medium mt-1">
                {{ docente.grado || "Sin grado académico" }}
              </p>
            </div>

            <!-- Score circle -->
            <div class="relative flex items-center justify-center">
              <div
                class="w-20 h-20 rounded-full flex items-center justify-center font-bold text-indigo-600"
                :style="circleStyle(docente.score_combinado)"
              >
                <div class="absolute w-16 h-16 bg-white rounded-full flex items-center justify-center text-lg">
                  {{ Math.round(docente.score_combinado) }}%
                </div>
              </div>
            </div>

          </div>

          <!-- Divider -->
          <div class="w-full h-px bg-gray-200 my-4"></div>

          <!-- Explicaciones SHAP -->
          <div v-if="docente.shap_explanations && Object.keys(docente.shap_explanations).length > 0" 
               class="mb-4 p-4 bg-blue-50 rounded-lg">
            <h4 class="text-sm font-semibold text-gray-700 mb-3">
              🔍 ¿Por qué esta recomendación?
            </h4>
            <div class="space-y-2">
              <div v-for="(value, feature) in getSortedShapValues(docente.shap_explanations)" 
                   :key="feature"
                   class="flex items-center gap-2">
                <span class="text-xs text-gray-600 w-32 flex-shrink-0">{{ formatFeatureName(feature) }}</span>
                <div class="flex-grow bg-gray-200 rounded-full h-4 overflow-hidden">
                  <div 
                    class="h-full rounded-full transition-all"
                    :class="value > 0 ? 'bg-green-500' : 'bg-red-500'"
                    :style="{ width: `${Math.min(Math.abs(value) * 100, 100)}%` }">
                  </div>
                </div>
                <span class="text-xs font-mono text-gray-700 w-16 text-right">
                  {{ value > 0 ? '+' : '' }}{{ value.toFixed(3) }}
                </span>
              </div>
            </div>
          </div>

          <!-- Detalles -->
          <div class="space-y-3 text-sm">

            <!-- Areas -->
            <div v-if="docente.evidencias.areas?.length">
              <p class="font-medium text-gray-700 mb-1">Áreas coincidentes:</p>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="a in docente.evidencias.areas"
                  :key="a"
                  class="px-3 py-1 rounded-full text-white bg-indigo-500 text-xs font-medium"
                >
                  {{ a }}
                </span>
              </div>
            </div>

            <!-- Lenguajes -->
            <div v-if="docente.evidencias.lenguajes?.length">
              <p class="font-medium text-gray-700 mb-1">Lenguajes:</p>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="l in docente.evidencias.lenguajes"
                  :key="l"
                  class="px-3 py-1 rounded-full text-white bg-cyan-500 text-xs font-medium"
                >
                  {{ l }}
                </span>
              </div>
            </div>

            <!-- Herramientas -->
            <div v-if="docente.evidencias.herramientas?.length">
              <p class="font-medium text-gray-700 mb-1">Herramientas:</p>
              <div class="flex flex-wrap gap-2">
                <span
                  v-for="h in docente.evidencias.herramientas"
                  :key="h"
                  class="px-3 py-1 rounded-full text-white bg-pink-500 text-xs font-medium"
                >
                  {{ h }}
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

    return {
      cursoNombre: computed(() => store.currentCursoNombre),
      recommendations: computed(() => store.recommendations),
      recommendationsSorted,
      loading,
      rankColor,
      circleStyle,
      goBack,
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
