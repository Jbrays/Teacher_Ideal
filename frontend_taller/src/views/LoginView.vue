<template>
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-500 to-purple-600 px-4">

    <div class="bg-white/90 backdrop-blur-md rounded-2xl shadow-xl p-8 w-full max-w-md animate-fadeIn">

      <!-- Título -->
      <h1 class="text-2xl font-bold text-gray-800 text-center mb-4">
        Sistema de Evaluación Docente
      </h1>

      <p class="text-gray-600 text-center mb-8">
        Inicia sesión con tu cuenta institucional
      </p>

      <!-- Botón Login Google -->
      <button
        @click="login"
        class="w-full bg-white border border-gray-300 shadow-sm rounded-lg py-3 flex items-center justify-center gap-3 text-gray-700 font-medium hover:bg-gray-50 transition"
      >
        <img src="https://www.svgrepo.com/show/475656/google-color.svg" class="w-5 h-5" alt="google" />
        Iniciar sesión con Google
      </button>

      <!-- Loading -->
      <div v-if="loading" class="mt-6 text-center text-gray-700">
        <span class="animate-pulse">Procesando...</span>
      </div>

    </div>

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

        // Guardar token de Google Drive
        localStorage.setItem("googleToken", result.googleToken);

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
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(15px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-fadeIn {
  animation: fadeIn 0.4s ease-out;
}
</style>
