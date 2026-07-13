<template>
  <div class="bg-surface text-on-surface font-body-lg min-h-screen flex flex-col w-full antialiased">
    <!-- TopAppBar -->
    <header class="bg-surface dark:bg-inverse-surface w-full z-10 sticky top-0 bg-surface-container dark:bg-surface-container-high border-b-0 shadow-none">
      <div class="flex justify-between items-center px-margin-mobile md:px-margin-desktop h-16 w-full">
        <div class="flex items-center gap-2">
          <button @click="$router.push('/ciclos')" class="text-on-surface hover:bg-surface-variant/50 transition-colors p-2 rounded-full cursor-pointer active:scale-95 transition-transform">
            <span class="material-symbols-outlined" data-icon="arrow_back">arrow_back</span>
          </button>
          <span class="font-title-lg text-title-lg font-bold text-primary dark:text-primary-fixed">Vektora</span>
        </div>
        <div class="flex items-center gap-4">
          <button @click="$router.push('/settings')" class="text-on-surface-variant hover:bg-surface-variant/50 dark:hover:bg-surface-variant/20 transition-colors p-2 rounded-full cursor-pointer active:scale-95 transition-transform">
            <span class="material-symbols-outlined" data-icon="settings">settings</span>
          </button>
          <div class="w-8 h-8 rounded-full border-2 border-primary-container bg-secondary-container text-on-secondary-container flex items-center justify-center cursor-pointer">
            <span class="material-symbols-outlined text-sm">person</span>
          </div>
        </div>
      </div>
    </header>

    <!-- Canvas -->
    <div class="p-margin-mobile md:p-margin-desktop flex-1 w-full">
      <div class="mb-8 hidden md:block">
        <div class="flex items-center gap-3 mb-2">
          <h2 class="font-headline-lg text-headline-lg font-bold text-on-surface uppercase">CURSOS – CICLO {{ ciclo }}</h2>
          <div v-if="isProcessingBackground" class="flex items-center group relative cursor-help" title="El sistema sigue procesando nuevos documentos en segundo plano. Los resultados actuales podrían cambiar.">
            <span class="material-symbols-outlined animate-spin text-primary opacity-80 text-2xl">sync</span>
          </div>
        </div>
        <p class="text-body-lg font-body-lg text-on-surface-variant">Selecciona el curso para visualizar el ranking de docentes.</p>
      </div>

      <!-- Mobile Welcome -->
      <div class="md:hidden mb-6">
        <h2 class="font-headline-lg-mobile text-headline-lg-mobile font-semibold text-on-surface uppercase">CICLO {{ ciclo }}</h2>
        <p class="text-body-md font-body-md text-on-surface-variant mt-1">Selecciona el curso para visualizar el ranking.</p>
      </div>

      <!-- NO DATA -->
      <div v-if="!cursos.length" class="bg-surface rounded-[28px] p-8 shadow-[0px_2px_8px_rgba(0,0,0,0.05)] border border-surface-variant text-center my-10">
        <h2 class="font-title-lg text-title-lg mb-2 text-on-surface uppercase">NO HAY CURSOS EN ESTE CICLO</h2>
        <p class="font-body-md text-body-md text-on-surface-variant mb-6">Procesa los sílabos o revisa el repositorio seleccionado.</p>
      </div>

      <!-- Courses Grid -->
      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <a 
          v-for="curso in cursos" 
          :key="curso.id" 
          @click="selectCurso(curso)"
          class="bg-surface rounded-[28px] p-6 shadow-[0px_2px_8px_rgba(0,0,0,0.05)] border border-surface-variant hover:border-primary-container transition-all cursor-pointer active:scale-95 flex flex-col group h-full"
        >
          <div class="flex justify-between items-start mb-2">
            <div class="w-12 h-12 rounded-[16px] bg-secondary-container text-on-secondary-container flex items-center justify-center">
              <span class="material-symbols-outlined">menu_book</span>
            </div>
            <span class="material-symbols-outlined text-outline group-hover:text-primary transition-colors" data-icon="arrow_forward">arrow_forward</span>
          </div>
          <div class="mt-4">
            <h3 class="font-title-lg text-title-lg text-on-surface mb-1 group-hover:text-primary transition-colors leading-tight uppercase">{{ curso.nombre }}</h3>
          </div>
        </a>
      </div>

    </div>
  </div>
</template>

<script>
import { useAppStore } from "../store/app";
import { useRouter, useRoute } from "vue-router";
import { computed, onMounted, onUnmounted, ref } from "vue";
import { fetchSystemStatus } from "../services/api";

export default {
  name: "CursosView",

  setup() {
    const store = useAppStore();
    const router = useRouter();
    const route = useRoute();

    // Obtener el ciclo de la URL
    const ciclo = computed(() => route.params.cicloId || store.currentCiclo);
    
    // Si el ciclo cambió, actualizarlo en el store
    if (ciclo.value && ciclo.value !== store.currentCiclo) {
      store.currentCiclo = ciclo.value;
    }

    const cursos = computed(() => store.cursosDelCiclo);
    const isProcessingBackground = ref(false);

    const selectCurso = (curso) => {
      const path = store.goToRecommendations(curso);
      router.push(path);
    };

    let pollingInterval = null;

    const checkSystemStatus = async () => {
      try {
        const status = await fetchSystemStatus();
        if (status) {
          isProcessingBackground.value = status.is_processing;
        }
      } catch (error) {
        console.error('Error verificando status:', error);
      }
    };

    onMounted(async () => {
      // Si no hay datos, intentar restaurar o cargar
      if (!store.hasData) {
        const restored = store.restoreState();
        
        if (!restored || !store.hasData) {
          // Redirigir a home para configurar
          router.push('/home');
        }
      }
      
      await checkSystemStatus();
      pollingInterval = setInterval(checkSystemStatus, 5000);
    });

    onUnmounted(() => {
      if (pollingInterval) clearInterval(pollingInterval);
    });

    return {
      ciclo,
      cursos,
      selectCurso,
      isProcessingBackground,
    };
  },
};
</script>
