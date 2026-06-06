<template>
  <div class="min-h-screen bg-surface">

    <!-- Header -->
    <header class="w-full bg-white shadow-sm py-4 px-6 flex items-center justify-between">
      <h1 class="text-xl font-semibold text-on-surface">
        Hola, {{ userName }}
      </h1>

      <button
        @click="$router.push('/settings')"
        class="w-10 h-10 flex items-center justify-center rounded-full bg-surface-container text-primary hover:bg-surface-dim transition shadow-sm"
      >
        ⚙️
      </button>
    </header>

    <!-- Contenido -->
    <div class="max-w-3xl mx-auto px-6 py-20 text-center">

      <!-- Mensaje de bienvenida simple -->
      <div class="animate-fadeIn bg-white p-10 rounded-28px shadow-sm">
        <h2 class="text-3xl font-bold text-on-surface mb-4">
          Academic Orchestrator
        </h2>

        <p class="text-outline text-lg mb-8 leading-relaxed">
          Sistema de Análisis de Talento Docente impulsado por IA. Mapeo semántico y recomendación de perfiles.
        </p>

        <p class="text-outline text-sm">
          Si aún no has configurado tus repositorios de datos, ve a los 
          <span class="inline-flex items-center gap-1 text-primary font-medium">
            ajustes ⚙️
          </span>
        </p>
      </div>

    </div>
  </div>
</template>

<script>
import { auth } from "../services/firebase";
import { useAppStore } from "../store/app";
import { useRouter } from "vue-router";
import { ref, onMounted } from "vue";

export default {
  name: "HomeView",

  setup() {
    const store = useAppStore();
    const router = useRouter();
    const userName = ref("Usuario");

    onMounted(async () => {
      // El usuario ya está autenticado (verificado por el router guard)
      const user = auth.currentUser;
      
      if (user) {
        userName.value = user.displayName || "Usuario";
      }
      
      // Intentar restaurar estado o cargar datos
      const restored = store.restoreState();
      
      if (restored && store.hasData) {
        // Si ya hay datos, ir directo a ciclos
        router.push('/ciclos');
      } else {
        // Intentar cargar desde backend
        try {
          const loaded = await store.loadCursosFromBackend();
          if (loaded) {
            router.push('/ciclos');
          }
        } catch (error) {
          console.log('No hay datos, mostrar configuración');
          // Quedarse en home para que configure
        }
      }
    });

    return {
      userName,
    };
  },
};
</script>

<style scoped>
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}
.animate-fadeIn {
  animation: fadeIn 0.4s ease-out;
}
</style>
