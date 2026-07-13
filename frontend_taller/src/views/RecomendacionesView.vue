<template>
  <div class="min-h-screen bg-background flex flex-col antialiased">

    <!-- TopAppBar Mobile (Visible on Mobile Only) -->
    <header class="md:hidden flex justify-between items-center px-margin-mobile h-16 w-full fixed top-0 left-0 z-50 bg-surface text-primary border-b border-surface-container-high shadow-sm transition-colors">
      <div class="flex items-center gap-4">
        <button @click="goBack" aria-label="Back" class="material-symbols-outlined text-on-surface hover:bg-surface-variant/50 p-2 rounded-full transition-colors cursor-pointer active:scale-95">arrow_back</button>
        <h1 class="font-title-lg text-title-lg font-bold text-primary">Vektora</h1>
      </div>
      <div class="flex items-center gap-2">
        <button @click="$router.push('/settings')" aria-label="Settings" class="material-symbols-outlined text-on-surface-variant hover:bg-surface-variant/50 p-2 rounded-full transition-colors cursor-pointer active:scale-95">settings</button>
      </div>
    </header>

    <!-- Main Content Canvas -->
    <main class="flex-1 w-full pt-16 md:pt-0 min-h-screen bg-background">
      <div class="px-margin-mobile md:px-margin-desktop py-8 md:py-12">
        
        <!-- Page Header -->
        <div class="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-8 md:mb-12">
          <div>
            <div class="flex items-center gap-2 mb-4 md:hidden">
              <button @click="goBack" class="material-symbols-outlined text-on-surface-variant hover:bg-surface-variant p-2 -ml-2 rounded-full transition-colors">arrow_back</button>
              <span class="font-label-lg text-label-lg text-on-surface-variant">Volver</span>
            </div>
            <div class="hidden md:flex items-center gap-2 mb-6">
              <button @click="goBack" class="flex items-center gap-2 text-on-surface-variant hover:text-primary transition-colors group">
                <span class="material-symbols-outlined group-hover:-translate-x-1 transition-transform">arrow_back</span>
                <span class="font-label-lg text-label-lg">Volver</span>
              </button>
            </div>
            <div class="flex items-center gap-3 mb-2">
              <h2 class="font-headline-lg-mobile md:font-headline-lg text-headline-lg-mobile md:text-headline-lg text-on-background uppercase">RANKING DE DOCENTES</h2>
              <div v-if="isProcessingBackground" class="flex items-center group relative cursor-help" title="El sistema sigue procesando nuevos documentos en segundo plano. Los resultados actuales podrían cambiar.">
                <span class="material-symbols-outlined animate-spin text-primary opacity-80 text-2xl">sync</span>
              </div>
            </div>
            <p class="font-body-lg text-body-lg text-on-surface-variant max-w-2xl uppercase">{{ cursoNombre }}</p>
          </div>
          <div class="flex items-center gap-3">
            <button 
              @click="handleExportPdf" 
              :disabled="exportingPdf || loading || !recommendations.length" 
              class="flex items-center gap-2 px-5 py-2.5 bg-primary text-on-primary rounded-full hover:opacity-90 disabled:opacity-50 transition-colors shadow-sm"
            >
              <span v-if="exportingPdf" class="material-symbols-outlined animate-spin text-[20px]">refresh</span>
              <span v-else class="material-symbols-outlined text-[20px]">picture_as_pdf</span>
              <span class="font-label-lg text-label-lg">{{ exportingPdf ? 'Generando PDF...' : 'Exportar a PDF' }}</span>
            </button>
          </div>
        </div>

        <!-- Loading -->
        <div v-if="loading" class="flex flex-col items-center justify-center py-20 gap-4">
          <span class="material-symbols-outlined animate-spin text-primary text-4xl">sync</span>
          <p class="font-body-lg text-on-surface-variant">Analizando perfiles de docentes e invocando XAI...</p>
        </div>

        <!-- Sin recomendaciones -->
        <div v-else-if="!recommendations.length" class="bg-surface rounded-[28px] p-12 text-center border border-surface-container-highest shadow-sm">
          <span class="material-symbols-outlined text-6xl text-outline-variant mb-4">search_off</span>
          <h2 class="font-title-lg text-title-lg text-on-surface mb-2 uppercase">NO HAY RECOMENDACIONES</h2>
          <p class="font-body-md text-body-md text-on-surface-variant">Revisa los datos procesados o selecciona otro curso.</p>
        </div>

        <!-- Bento Grid Layout for Teachers -->
        <div v-else class="grid grid-cols-1 xl:grid-cols-2 gap-gutter-desktop">
          
          <div 
            v-for="(docente, index) in recommendationsSorted" 
            :key="docente.docente_id"
            class="bg-surface rounded-[28px] p-6 shadow-[0px_2px_8px_rgba(0,0,0,0.05)] border border-surface-container-highest hover:shadow-md transition-shadow relative overflow-hidden group flex flex-col h-full"
          >
            <!-- Subtle gradient background for top rank -->
            <div v-if="index === 0" class="absolute top-0 right-0 w-64 h-64 bg-primary-container/20 rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none"></div>
            
            <div class="flex justify-between items-start mb-6 relative z-10">
              <div class="flex items-center gap-4">
                <span class="font-display-lg text-display-lg font-black text-outline-variant opacity-40 w-12 text-center">{{ index + 1 }}</span>
                <div class="w-16 h-16 rounded-full bg-surface-container overflow-hidden border-2 border-surface flex-shrink-0 flex items-center justify-center text-primary-container">
                  <span class="material-symbols-outlined text-3xl">person</span>
                </div>
                <div>
                  <h3 class="font-title-lg text-title-lg text-on-surface mb-1 capitalize">{{ docente.nombre ? docente.nombre.toLowerCase() : '' }}</h3>
                </div>
              </div>
              <div class="flex flex-col items-end gap-2">
                <div :class="index === 0 ? 'bg-primary/10 text-primary' : 'bg-surface-container-high text-on-surface'" class="px-4 py-2 rounded-full font-title-md text-title-md font-bold flex items-center gap-2">
                  <span v-if="index === 0" class="material-symbols-outlined fill text-sm">trophy</span>
                  {{ Math.round(docente.score_combinado) }}%
                </div>
                <button @click="handleDelete(docente)" aria-label="Borrar datos de docente" class="text-error hover:bg-error-container/50 p-2 rounded-full transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100" title="Derecho al Olvido: Purgar datos de este docente">
                  <span class="material-symbols-outlined">delete</span>
                </button>
              </div>
            </div>

<div v-if="docente.perfil_tecnico?.length" class="flex flex-wrap gap-2 mb-6 relative z-10">
              <span
                v-for="(item, idx) in docente.perfil_tecnico.slice(0, 5)"
                :key="idx"
                class="px-2 py-1 rounded-[8px] bg-surface-container text-on-surface-variant font-label-md text-label-md"
              >
                {{ item.es }}
              </span>
              <span v-if="docente.perfil_tecnico.length > 5" class="px-2 py-1 rounded-[8px] bg-surface-container text-on-surface-variant font-label-md text-label-md">...</span>
            </div>

            <!-- XAI Section -->
            <div class="mt-auto pt-4 border-t border-surface-container-high relative z-10 flex-grow flex flex-col">
              <label class="font-label-md text-label-md text-on-surface-variant mb-2 flex items-center gap-2">
                <span class="material-symbols-outlined text-[18px]">psychiatry</span>
                Motivos
              </label>
              <div class="w-full bg-surface-container-lowest border border-outline-variant rounded-xl p-4 font-body-md text-body-md text-on-surface overflow-y-auto max-h-[150px] leading-relaxed whitespace-pre-wrap">
                {{ docente.xai_explanations || 'No hay explicaciones disponibles para este perfil.' }}
              </div>
            </div>
          </div>

        </div>

      </div>
    </main>
  </div>
</template>

<script>
import { useAppStore } from "../store/app";
import { useRouter, useRoute } from "vue-router";
import { computed, onMounted, onUnmounted, ref } from "vue";
import { deleteDocente, fetchSystemStatus, exportCursoRecommendationsPdf } from "../services/api";

export default {
  name: "RecommendationsView",

  setup() {
    const store = useAppStore();
    const router = useRouter();
    const route = useRoute();
    const loading = ref(true);
    const isProcessingBackground = ref(false);
    const exportingPdf = ref(false);
    let pollInterval = null;

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

      // Iniciar polling
      const checkStatus = async () => {
        const status = await fetchSystemStatus();
        isProcessingBackground.value = status.is_processing;
      };
      checkStatus(); // Primera llamada inmediata
      pollInterval = setInterval(checkStatus, 3000); // Poll cada 3s
    });

    onUnmounted(() => {
      if (pollInterval) clearInterval(pollInterval);
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

    const handleExportPdf = async () => {
      exportingPdf.value = true;
      try {
        await exportCursoRecommendationsPdf(cursoId, store.currentCursoNombre);
      } catch (error) {
        alert("Error exportando PDF: " + error.message);
      } finally {
        exportingPdf.value = false;
      }
    };

    return {
      cursoNombre: computed(() => store.currentCursoNombre),
      recommendations: computed(() => store.recommendations),
      recommendationsSorted,
      loading,
      isProcessingBackground,
      exportingPdf,
      rankColor,
      circleStyle,
      goBack,
      handleDelete,
      handleExportPdf,
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
