<template>
  <div class="bg-background text-on-background min-h-screen flex overflow-hidden selection:bg-primary-container selection:text-on-primary-container">
    <!-- Main Content Area -->
    <div class="flex-1 flex flex-col h-screen overflow-hidden bg-background">
      <!-- TopAppBar (Shared Component) -->
      <header class="w-full z-10 sticky top-0 bg-surface border-b-0 shadow-none">
        <div class="flex justify-between items-center px-margin-mobile md:px-margin-desktop h-16 w-full">
          <!-- Brand -->
          <div class="flex items-center gap-4 text-primary">
            <div class="w-10 h-10 rounded-xl bg-primary-container text-on-primary-container flex items-center justify-center">
              <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">deployed_code</span>
            </div>
            <span class="font-title-lg text-title-lg font-bold">Vektora</span>
          </div>
          <!-- Empty spacer for desktop to push actions right -->
          <div class="hidden md:block flex-1"></div>
          <!-- Trailing Actions & Profile -->
          <div class="flex items-center gap-6">
            <!-- User Greeting -->
            <div class="hidden sm:flex flex-col items-end justify-center">
              <span class="font-label-lg text-label-lg text-on-surface">Hola, {{ userName }}</span>
            </div>
            <!-- Settings Action -->
            <button @click="$router.push('/settings')" class="flex items-center gap-2 text-on-surface-variant hover:bg-surface-variant/50 px-3 py-2 rounded-full cursor-pointer active:scale-95 transition-all">
              <span class="material-symbols-outlined">settings</span>
              <span class="font-label-lg text-label-lg hidden md:block">Configuración</span>
            </button>
            <!-- Profile Avatar -->
            <div class="w-10 h-10 rounded-full bg-secondary-container flex items-center justify-center cursor-pointer hover:opacity-80 transition-opacity text-on-secondary-container">
              <span class="material-symbols-outlined">person</span>
            </div>
          </div>
        </div>
      </header>
      
      <!-- Canvas (Dashboard Empty State) -->
      <main class="flex-1 overflow-y-auto p-gutter-mobile md:p-margin-desktop flex items-center justify-center relative">
        <!-- Background Decorative Blob (Subtle) -->
        <div class="absolute inset-0 z-0 flex items-center justify-center opacity-30 pointer-events-none">
          <div class="w-[600px] h-[600px] bg-primary-container rounded-full blur-[120px] mix-blend-multiply"></div>
          <div class="w-[500px] h-[500px] bg-tertiary-container rounded-full blur-[100px] mix-blend-multiply absolute translate-x-32 -translate-y-16"></div>
        </div>
        <!-- Empty State Content Container -->
        <div class="relative z-10 max-w-2xl w-full flex flex-col items-center text-center p-12">
          <!-- Illustrative Icon -->
          <div class="w-32 h-32 mb-8 rounded-full bg-surface-container-high flex items-center justify-center shadow-[0px_2px_8px_rgba(0,0,0,0.05)] border border-outline-variant/30">
            <span class="material-symbols-outlined text-6xl text-primary" style="font-variation-settings: 'FILL' 0, 'wght' 200;">deployed_code</span>
          </div>
          <!-- Text Content -->
          <h2 class="font-display-lg text-display-lg md:text-5xl font-light text-on-surface tracking-tight mb-4 uppercase">
            <div class="flex items-center justify-center gap-4">
              BIENVENIDO AL PORTAL ACADÉMICO
              <div v-if="isProcessingBackground" class="flex items-center group relative cursor-help" title="El sistema sigue procesando nuevos documentos en segundo plano.">
                <span class="material-symbols-outlined animate-spin text-primary opacity-80 text-4xl">sync</span>
              </div>
            </div>
          </h2>
          <p class="font-body-lg text-body-lg text-on-surface-variant max-w-lg mb-10 leading-relaxed">
            Tu espacio de trabajo está listo. Aún no hay datos en tu panel principal. Ve a la configuración para comenzar a procesar tus documentos y establecer tus ciclos académicos.
          </p>
          <!-- Primary Action Button -->
          <button @click="$router.push('/settings')" class="group flex items-center gap-3 bg-primary hover:bg-primary/90 text-on-primary px-8 py-4 rounded-full font-label-lg text-label-lg shadow-[0px_4px_12px_rgba(53,37,205,0.2)] transition-all active:scale-95">
            <span class="material-symbols-outlined transition-transform group-hover:rotate-90">settings</span>
            Ir a Configuración
          </button>
        </div>
      </main>
    </div>
  </div>
</template>

<script>
import { auth } from "../services/firebase";
import { useAppStore } from "../store/app";
import { useRouter } from "vue-router";
import { ref, onMounted, onUnmounted } from "vue";
import { fetchSystemStatus } from "../services/api";

export default {
  name: "HomeView",

  setup() {
    const store = useAppStore();
    const router = useRouter();
    const userName = ref("Usuario");
    const isProcessingBackground = ref(false);
    let pollingInterval = null;

    const checkSystemStatus = async () => {
      const status = await fetchSystemStatus();
      isProcessingBackground.value = status.is_processing;
    };

    onMounted(async () => {
      // El usuario ya está autenticado (verificado por el router guard)
      const user = auth.currentUser;
      
      if (user) {
        userName.value = user.displayName || "Usuario";
      }

      await checkSystemStatus();
      pollingInterval = setInterval(checkSystemStatus, 3000);
      
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

    onUnmounted(() => {
      if (pollingInterval) clearInterval(pollingInterval);
    });

    return {
      userName,
      isProcessingBackground,
    };
  },
};
</script>

<style scoped>
/* Scoped styles are handled by tailwind classes and global CSS */
</style>
