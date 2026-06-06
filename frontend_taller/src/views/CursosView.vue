<template>
  <div class="min-h-screen bg-surface">

    <!-- Header -->
    <header class="w-full bg-white shadow-sm py-4 px-6 flex items-center justify-between">
      <button
        @click="$router.push('/ciclos')"
        class="w-10 h-10 flex items-center justify-center rounded-full bg-surface hover:bg-surface-dim text-on-surface transition"
      >
        ←
      </button>

      <h1 class="text-xl font-semibold text-on-surface">
        Cursos – Ciclo {{ ciclo }}
      </h1>

      <button
        @click="$router.push('/settings')"
        class="w-10 h-10 flex items-center justify-center rounded-full bg-surface-container text-primary hover:bg-surface-dim transition shadow-sm"
      >
        ⚙️
      </button>
    </header>

    <!-- Content -->
    <div class="content max-w-4xl mx-auto px-6 py-10">

      <!-- No cursos -->
      <div v-if="!cursos.length" class="text-center mt-20 text-outline">
        <h2 class="text-xl font-semibold mb-3">No hay cursos en este ciclo</h2>
        <p>Procesa los sílabos o revisa el repositorio seleccionado.</p>
      </div>

      <!-- Lista de cursos -->
      <div v-else class="flex flex-col gap-4">

        <div
          v-for="curso in cursos"
          :key="curso.id"
          @click="selectCurso(curso)"
          class="bg-white p-6 rounded-28px shadow-sm hover:shadow-md cursor-pointer border border-transparent hover:border-surface-dim transition-shadow"
        >
          <h3 class="text-lg font-semibold text-on-surface">{{ curso.nombre }}</h3>

          <p v-if="curso.codigo" class="text-outline text-sm mt-1">
            Código: {{ curso.codigo }}
          </p>
        </div>

      </div>

    </div>

  </div>
</template>

<script>
import { useAppStore } from "../store/app";
import { useRouter, useRoute } from "vue-router";
import { computed, onMounted } from "vue";

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

    const selectCurso = (curso) => {
      const path = store.goToRecommendations(curso);
      router.push(path);
    };

    onMounted(() => {
      // Si no hay datos, intentar restaurar o cargar
      if (!store.hasData) {
        const restored = store.restoreState();
        
        if (!restored || !store.hasData) {
          // Redirigir a home para configurar
          router.push('/home');
        }
      }
    });

    return {
      ciclo,
      cursos,
      selectCurso,
    };
  },
};
</script>
