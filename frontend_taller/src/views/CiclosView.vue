<template>
  <div class="min-h-screen bg-gray-100">
    
    <!-- Header -->
    <header class="w-full bg-white shadow-sm py-4 px-6 flex items-center justify-between">
      <div></div>
      <h1 class="text-xl font-semibold text-gray-800">Selecciona un Ciclo</h1>
      <button
        @click="$router.push('/settings')"
        class="text-gray-600 hover:text-indigo-500 transition text-xl"
      >
        ⚙️
      </button>
    </header>

    <!-- Content -->
    <div class="content max-w-4xl mx-auto px-6 py-10">
      
      <!-- NO DATA -->
      <div v-if="!ciclos.length" class="text-center text-gray-600 mt-20">
        <h2 class="text-xl font-semibold mb-3">No hay ciclos disponibles</h2>
        <p class="text-gray-500 mb-6">Configura las carpetas y procesa los archivos primero.</p>
        <button
          @click="$router.push('/settings')"
          class="bg-indigo-600 hover:bg-indigo-700 text-white py-2 px-6 rounded-xl font-semibold shadow"
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
          class="bg-white shadow hover:shadow-lg transition cursor-pointer p-8 rounded-2xl text-center border border-transparent hover:border-indigo-500"
        >
          <h3 class="text-2xl font-semibold text-indigo-700">Ciclo {{ ciclo }}</h3>
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
