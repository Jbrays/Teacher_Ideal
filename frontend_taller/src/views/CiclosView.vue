<template>
  <div class="bg-surface text-on-surface font-body-lg min-h-screen flex flex-col w-full antialiased">
    <!-- TopAppBar -->
    <header class="bg-surface dark:bg-inverse-surface w-full z-10 sticky top-0 bg-surface-container dark:bg-surface-container-high border-b-0 shadow-none">
      <div class="flex justify-between items-center px-margin-mobile md:px-margin-desktop h-16 w-full">
        <div class="flex items-center">
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
          <h2 class="font-headline-lg text-headline-lg font-bold text-on-surface uppercase">PANEL DE CICLOS</h2>
          <div v-if="isProcessingBackground" class="flex items-center group relative cursor-help" title="El sistema sigue procesando nuevos documentos en segundo plano. Los resultados actuales podrían cambiar.">
            <span class="material-symbols-outlined animate-spin text-primary opacity-80 text-2xl">sync</span>
          </div>
        </div>
        <p class="text-body-lg font-body-lg text-on-surface-variant">Resumen de los ciclos académicos disponibles.</p>
      </div>

      <!-- Mobile Welcome -->
      <div class="md:hidden mb-6">
        <h2 class="font-headline-lg-mobile text-headline-lg-mobile font-semibold text-on-surface uppercase">PANEL DE CICLOS</h2>
        <p class="text-body-md font-body-md text-on-surface-variant mt-1">Resumen de los ciclos académicos disponibles.</p>
      </div>

      <!-- NO DATA -->
      <div v-if="!ciclos.length" class="bg-surface rounded-[28px] p-8 shadow-[0px_2px_8px_rgba(0,0,0,0.05)] border border-surface-variant text-center my-10">
        <h2 class="font-title-lg text-title-lg mb-2 text-on-surface uppercase">NO HAY CICLOS DISPONIBLES</h2>
        <p class="font-body-md text-body-md text-on-surface-variant mb-6">Configura los repositorios y procesa los archivos primero.</p>
        <button
          @click="$router.push('/settings')"
          class="inline-flex items-center gap-2 bg-primary hover:bg-primary/90 text-on-primary px-6 py-3 rounded-full font-label-lg transition-colors shadow-sm"
        >
          <span class="material-symbols-outlined text-sm">settings</span>
          Ir a Configuración
        </button>
      </div>

      <!-- Cycle Cards Grid -->
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
        <a 
          v-for="(ciclo, index) in ciclos" 
          :key="ciclo" 
          @click="selectCiclo(ciclo)"
          class="bg-surface rounded-[28px] p-6 shadow-[0px_2px_8px_rgba(0,0,0,0.05)] border border-surface-variant hover:border-primary-container transition-all cursor-pointer active:scale-95 flex flex-col group h-full"
        >
          <div class="flex justify-between items-start mb-4">
            <div class="w-12 h-12 rounded-full bg-primary-container text-on-primary-container flex items-center justify-center">
              <span class="font-title-lg text-title-lg font-bold">{{ index + 1 }}</span>
            </div>
            <span class="material-symbols-outlined text-outline group-hover:text-primary transition-colors" data-icon="arrow_forward">arrow_forward</span>
          </div>
          <div class="mt-auto">
            <h3 class="font-title-lg text-title-lg text-on-surface mb-1 group-hover:text-primary transition-colors uppercase">CICLO {{ ciclo }}</h3>
            <p class="font-body-md text-body-md text-on-surface-variant">Semestre Académico</p>
            <div class="mt-4 flex gap-2">
              <span class="inline-flex items-center px-2 py-1 rounded-[8px] bg-secondary/10 text-secondary font-label-md text-label-md">Processed</span>
            </div>
          </div>
        </a>
      </div>

    </div>
  </div>
</template>

<script>
import { useAppStore } from "../store/app";
import { useRouter } from "vue-router";
import { computed, onMounted, onUnmounted, ref } from "vue";
import { fetchSystemStatus } from "../services/api";

export default {
  name: "CiclosView",

  setup() {
    const store = useAppStore();
    const router = useRouter();
    let pollingInterval = null;

    const ciclos = computed(() => store.ciclos);
    const isProcessingBackground = ref(false);

    const selectCiclo = (ciclo) => {
      const path = store.goToCursos(ciclo);
      router.push(path);
    };

    // Función para cargar silenciosamente
    const fetchSilencioso = async () => {
      try {
        await store.loadCursosFromBackend();
      } catch (error) {
        console.error('Error en auto-recarga de ciclos:', error);
      }
    };

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
      // Restauramos estado local por si acaso
      store.restoreState();
      
      // Siempre forzamos una carga fresca al entrar a la vista
      await fetchSilencioso();
      await checkSystemStatus();

      // Iniciamos el Polling (Opción B) cada 5 segundos
      pollingInterval = setInterval(() => {
        fetchSilencioso();
        checkSystemStatus();
      }, 5000);
    });

    onUnmounted(() => {
      // Destruimos el polling al salir de la pantalla para no consumir recursos
      if (pollingInterval) clearInterval(pollingInterval);
    });

    return {
      ciclos,
      selectCiclo,
      isProcessingBackground,
    };
  },
};
</script>
