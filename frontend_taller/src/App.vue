<template>
  <router-view />
</template>

<script>
import { onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { onAuthStateChanged } from 'firebase/auth';
import { useAppStore } from './store/app';
import {
  auth,
  logoutFirebase,
  startDriveTokenKeepAlive,
  stopDriveTokenKeepAlive,
} from './services/firebase';

export default {
  setup() {
    const router = useRouter();
    const store = useAppStore();
    let inactivityTimer = null;
    let unsubAuth = null;
    const INACTIVITY_TIME = 90 * 60 * 1000; // 90 minutos

    const resetTimer = () => {
      if (inactivityTimer) clearTimeout(inactivityTimer);
      inactivityTimer = setTimeout(logoutDueToInactivity, INACTIVITY_TIME);
    };

    const logoutDueToInactivity = async () => {
      console.warn("Cerrando sesión por inactividad...");
      try {
        await logoutFirebase();
        store.clearState();
        localStorage.removeItem("googleToken");
        localStorage.removeItem("firebase_id_token");
        router.push('/login');
      } catch (error) {
        console.error("Error al cerrar sesión por inactividad:", error);
      }
    };

    onMounted(() => {
      window.addEventListener('mousemove', resetTimer);
      window.addEventListener('mousedown', resetTimer);
      window.addEventListener('keypress', resetTimer);
      window.addEventListener('touchmove', resetTimer);
      resetTimer();

      // Si hay sesión Firebase al recargar, mantener tokens Drive vivos en backend
      unsubAuth = onAuthStateChanged(auth, (user) => {
        if (user) {
          startDriveTokenKeepAlive();
        } else {
          stopDriveTokenKeepAlive();
        }
      });
    });

    onUnmounted(() => {
      if (inactivityTimer) clearTimeout(inactivityTimer);
      if (unsubAuth) unsubAuth();
      window.removeEventListener('mousemove', resetTimer);
      window.removeEventListener('mousedown', resetTimer);
      window.removeEventListener('keypress', resetTimer);
      window.removeEventListener('touchmove', resetTimer);
    });

    return {};
  }
};
</script>

<style>
html, body {
  margin: 0;
  padding: 0;
  background-color: theme('colors.background');
  color: theme('colors.on-background');
  font-family: 'Hanken Grotesk', sans-serif;
}
.material-symbols-outlined {
  font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
}
.material-symbols-outlined.fill {
  font-variation-settings: 'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24;
}

/* Custom scrollbar for textareas */
textarea::-webkit-scrollbar {
  width: 6px;
}
textarea::-webkit-scrollbar-track {
  background: transparent;
}
textarea::-webkit-scrollbar-thumb {
  background-color: theme('colors.outline-variant');
  border-radius: 20px;
}
</style>
