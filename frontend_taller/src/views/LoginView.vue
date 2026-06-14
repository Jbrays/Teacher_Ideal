<template>
  <div class="bg-surface text-on-surface min-h-screen flex flex-col justify-center items-center relative overflow-hidden selection:bg-primary-container selection:text-on-primary-container">
    <!-- Ambient Background Depth Layers -->
    <div class="fixed top-[-10%] left-[-5%] w-[500px] h-[500px] bg-primary-container rounded-full mix-blend-multiply filter blur-[120px] opacity-[0.15] pointer-events-none"></div>
    <div class="fixed bottom-[-10%] right-[-5%] w-[600px] h-[600px] bg-secondary-container rounded-full mix-blend-multiply filter blur-[120px] opacity-[0.15] pointer-events-none"></div>
    
    <main class="w-full max-w-md px-margin-mobile relative z-10">
      <!-- Main Card Container -->
      <div class="bg-surface-container-lowest rounded-[28px] p-8 md:p-12 shadow-[0px_2px_8px_rgba(0,0,0,0.05)] flex flex-col items-center border border-surface-container-high/50">
        <!-- Brand Icon Anchor -->
        <div class="w-16 h-16 rounded-[16px] bg-primary-container flex items-center justify-center mb-6 shadow-sm">
          <span class="material-symbols-outlined text-4xl text-on-primary-container" style="font-variation-settings: 'FILL' 1;">
            account_tree
          </span>
        </div>
        
        <!-- Header Typography -->
        <h1 class="font-headline-lg text-headline-lg text-on-surface text-center mb-2 tracking-tight">
          Vektora
        </h1>
        <p class="font-body-md text-body-md text-on-surface-variant text-center mb-8 max-w-[280px]">
          Acceda a su portal de gestión administrativa y de investigación.
        </p>

        <!-- Primary Action: Google SSO -->
        <button 
          @click="login" 
          :disabled="loading"
          class="w-full flex items-center justify-center gap-3 bg-surface-container-lowest border border-outline text-on-surface rounded-full py-3.5 px-6 hover:bg-surface-variant hover:border-outline-variant transition-all duration-200 focus:ring-2 focus:ring-primary focus:outline-none mb-6 group disabled:opacity-50"
        >
          <svg v-if="!loading" class="w-5 h-5 flex-shrink-0" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"></path>
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"></path>
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"></path>
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"></path>
          </svg>
          <span v-if="loading" class="material-symbols-outlined animate-spin w-5 h-5 flex-shrink-0 text-outline">sync</span>
          <span class="font-label-lg text-label-lg group-hover:text-primary transition-colors">
            {{ loading ? 'Procesando...' : 'Iniciar sesión con Google' }}
          </span>
        </button>
      </div>

      <!-- Utility Footer -->
      <div class="mt-8 text-center flex flex-col gap-2">
        <p class="font-label-md text-label-md text-on-surface-variant">
          ¿No tiene una cuenta administrativa? <a class="text-primary hover:underline font-semibold" href="#">Solicitar acceso</a>
        </p>
        <p class="font-body-md text-body-md text-outline text-[12px]">
          © 2024 Vektora. Red Segura.
        </p>
      </div>
    </main>
  </div>
</template>

<script>
import { loginWithGoogle } from "../services/firebase";
import { useAppStore } from "../store/app";
import { useRouter } from "vue-router";
import { ref } from "vue";

export default {
  name: "LoginView",

  setup() {
    const store = useAppStore();
    const router = useRouter();
    const loading = ref(false);

    const login = async () => {
      try {
        loading.value = true;

        const result = await loginWithGoogle();

        // Guardar usuario y tokens en el store
        store.setUser(result.user);
        store.setTokens({
          google: result.googleToken,
          firebase: await result.user.getIdToken()
        });

        // Guardar token de Google Drive y su expiración (55 mins)
        localStorage.setItem("googleToken", result.googleToken);
        localStorage.setItem("googleToken_expires_at", Date.now() + 55 * 60 * 1000);

        router.push("/home");

      } catch (error) {
        console.error("Error al iniciar sesión:", error);
        alert("No se pudo iniciar sesión: " + error.message);
      } finally {
        loading.value = false;
      }
    };

    return {
      loading,
      login,
    };
  },
};
</script>

<style scoped>
/* Scoped styles are mostly handled by tailwind classes and global CSS now */
</style>
