<template>
  <div class="min-h-screen bg-surface">
    
    <!-- Header -->
    <header class="w-full bg-white shadow-sm py-4 px-6 flex items-center justify-between">
      <div></div>
      <h1 class="text-xl font-semibold text-on-surface">Selecciona un Ciclo</h1>
      <button
        @click="$router.push('/settings')"
        class="w-10 h-10 flex items-center justify-center rounded-full bg-surface-container text-primary hover:bg-surface-dim transition shadow-sm"
      >
        ⚙️
      </button>
    </header>

    <!-- Content -->
    <div class="content max-w-4xl mx-auto px-6 py-10">
      
      <!-- NO DATA -->
      <div v-if="!ciclos.length" class="text-center text-outline mt-20">
        <h2 class="text-xl font-semibold mb-3">No hay ciclos disponibles</h2>
        <p class="mb-6">Configura los repositorios y procesa los archivos primero.</p>
        <button
          @click="$router.push('/settings')"
          class="bg-primary hover:bg-primary-container text-white py-2 px-6 rounded-full font-semibold shadow-sm transition-colors"
        >
          Ir a Configuración
        </button>
      </div>

      <!-- LISTA DE CICLOS -->
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        <div
          v-for="ciclo in ciclos"
          :key="ciclo"
          @click="selectCiclo(ciclo)"
          class="bg-white shadow-sm hover:shadow-md transition-shadow cursor-pointer p-8 rounded-28px text-center border border-transparent hover:border-surface-dim"
        >
          <h3 class="text-2xl font-semibold text-primary">Ciclo {{ ciclo }}</h3>
        </div>
      </div>

    </div>
  </div>
</template>

<script>
import { useAppStore } from "../store/app";
import { useRouter } from "vue-router";
import { computed, onMounted } from "vue";

export default {
  name: "CiclosView",

  setup() {
    const store = useAppStore();
    const router = useRouter();

    const ciclos = computed(() => store.ciclos);

    const selectCiclo = (ciclo) => {
      const path = store.goToCursos(ciclo);
      router.push(path);
    };

    // Cargar datos si no existen
    onMounted(async () => {
      if (!store.hasData) {
        const restored = store.restoreState();
        
        if (!restored || !store.hasData) {
          // Intentar cargar desde backend
          try {
            await store.loadCursosFromBackend();
          } catch (error) {
            console.error('Error cargando datos:', error);
          }
        }
      }
    });

    return {
      ciclos,
      selectCiclo,
    };
  },
};
</script>
