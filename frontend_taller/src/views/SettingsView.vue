<template>
  <div class="min-h-screen bg-surface">

    <header class="w-full bg-white shadow-sm py-4 px-6 flex items-center justify-between">
      <button
        @click="goBack"
        class="text-outline text-lg hover:text-primary transition"
      >
        ← Atrás
      </button>

      <h1 class="text-xl font-semibold text-on-surface">
        Configuración
      </h1>

      <div></div> </header>

    <div class="max-w-3xl mx-auto px-6 py-10">

      <div class="bg-white shadow-sm hover:shadow-md transition-shadow rounded-28px p-8 mb-8 border border-transparent hover:border-surface-dim">
        <h2 class="text-lg font-semibold text-on-surface mb-4">Usuario</h2>

        <p class="text-outline font-medium">
          {{ userEmail }}
        </p>

        <button
          @click="logout"
          class="mt-6 w-full bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 py-3 rounded-full font-semibold transition-colors"
        >
          Cerrar sesión
        </button>
      </div>

      <div class="bg-white shadow-sm hover:shadow-md transition-shadow rounded-28px p-8 mb-8 border border-transparent hover:border-surface-dim">
        <h2 class="text-lg font-semibold text-on-surface mb-4">Carpetas de Datos</h2>

        <p class="text-outline mb-6 text-sm">
          Selecciona los repositorios para procesar los archivos.
          <strong>Todas son obligatorias.</strong>
        </p>

        <div v-for="folder in folderList" :key="folder.key" class="mb-5">
          <label class="block font-semibold text-on-surface mb-2">
            {{ folder.icon }} {{ folder.label }}
            <span v-if="folder.optional" class="text-outline text-xs font-normal">(opcional)</span>
          </label>

          <button
            @click="selectFolderHandler(folder.key)"
            class="w-full bg-surface-container hover:bg-surface-dim text-primary py-3 rounded-full font-semibold transition-colors border border-surface-dim"
          >
            {{ folderState[folder.key]?.id ? 'Cambiar repositorio' : 'Seleccionar repositorio' }}
          </button>

          <p v-if="folderState[folder.key]?.id" class="text-sm font-medium text-green-700 mt-2 mb-1">
            Vinculado: "{{ folderState[folder.key].name }}"
          </p>
        </div>

        <div class="border-t border-surface-container my-8"></div>

        <button
          :disabled="!allFoldersSelected || isAnyProcessing || isSynced"
          @click="processData"
          class="w-full bg-primary hover:bg-primary-container text-white py-4 rounded-full font-semibold shadow-sm transition-colors disabled:bg-surface-dim disabled:text-outline disabled:cursor-not-allowed"
        >
          <span v-if="isSynced">Sincronización completada ✓</span>
          <span v-else-if="isAnyProcessing">Procesando...</span>
          <span v-else>Guardar Configuración y Sincronizar Todo</span>
        </button>

        <p v-if="processStatus" class="text-outline text-sm mt-4 whitespace-pre-line text-center font-medium">
          {{ processStatus }}
        </p>

        <p v-if="errorMessage" class="text-red-600 bg-red-50 p-3 rounded-lg border border-red-200 text-sm mt-4">
          ❌ {{ errorMessage }}
        </p>
      </div>

    </div>
  </div>
</template>

<script>
import { signOut } from "firebase/auth";
import { auth } from "../services/firebase";
import { selectFolder, processAllData, configWebhook } from "../services/drive";
import { useAppStore } from "../store/app";
import { useRouter } from "vue-router";
import { ref, computed, onMounted } from "vue";

export default {
  name: "SettingsView",

  setup() {
    const store = useAppStore();
    const router = useRouter();
    const userEmail = ref("");
    const isSynced = ref(false);
    
    // Estado de procesamiento individual
    const processingState = ref({
      cvs: false,
      syllabi: false,
      schedules: false
    });
    
    // Estado para verificar si el webhook está activo
    const webhookActive = ref({
      cvs: false,
      syllabi: false,
      schedules: false
    });
    
    const processStatus = ref("");
    const errorMessage = ref("");

    const folderState = ref({
      cvs: store.folders.cvs,
      syllabi: store.folders.syllabi,
      schedules: store.folders.schedules,
    });

    const folderList = [
      { key: "cvs", label: "CVs", icon: "📄", optional: false },
      { key: "syllabi", label: "Sílabos", icon: "📘", optional: false },
      { key: "schedules", label: "Horarios", icon: "📅", optional: false },
    ];

    const allFoldersSelected = computed(() => {
      return (
        folderState.value.cvs &&
        folderState.value.syllabi &&
        folderState.value.schedules
      );
    });

    const isAnyProcessing = computed(() => {
      return Object.values(processingState.value).some(v => v);
    });

    onMounted(() => {
      const user = auth.currentUser;
      if (user) {
        userEmail.value = user.email || "Usuario";
      }

      folderState.value = {
        cvs: store.folders.cvs,
        syllabi: store.folders.syllabi,
        schedules: store.folders.schedules,
      };

      // Verificar sincronización previa
      const syncedStr = localStorage.getItem('teacher_ideal_synced_folders');
      if (syncedStr) {
        try {
          const syncedData = JSON.parse(syncedStr);
          if (
            syncedData.cvs === folderState.value.cvs?.id &&
            syncedData.syllabi === folderState.value.syllabi?.id &&
            syncedData.schedules === folderState.value.schedules?.id &&
            folderState.value.cvs?.id
          ) {
            isSynced.value = true;
          }
        } catch (e) {
          console.error("Error parseando synced folders:", e);
        }
      }
    });

    const goBack = () => {
      if (store.hasData) {
        router.push('/ciclos');
      } else {
        router.push('/home');
      }
    };

    const logout = async () => {
      try {
        await signOut(auth);
        store.clearState();
        localStorage.removeItem('googleToken');
        localStorage.removeItem('firebase_id_token');
        router.push('/login');
      } catch (error) {
        console.error("Error cerrando sesión:", error);
      }
    };

    const selectFolderHandler = async (type) => {
      try {
        errorMessage.value = "";
        const folder = await selectFolder(type);
        
        if (folder) {
          folderState.value[type] = folder;
          store.setFolder(type, folder);
          
          // Limpiar localstorage y habilitar boton
          const syncedStr = localStorage.getItem('teacher_ideal_synced_folders');
          if (syncedStr) {
            try {
              const syncedData = JSON.parse(syncedStr);
              delete syncedData[type];
              localStorage.setItem('teacher_ideal_synced_folders', JSON.stringify(syncedData));
            } catch(e) {}
          }
          isSynced.value = false;
        }
      } catch (error) {
        console.error(`Error seleccionando carpeta ${type}:`, error);
        errorMessage.value = `Error seleccionando carpeta: ${error.message}`;
      }
    };

    const getGoogleToken = () => {
      const token = localStorage.getItem('googleToken');
      if (!token) throw new Error("No se encontró el token de Google. Inicia sesión nuevamente.");
      return token;
    };

    const processData = async () => {
      if (!allFoldersSelected.value) {
        errorMessage.value = "Falta seleccionar una o más carpetas.";
        return;
      }

      try {
        processingState.value.cvs = true;
        processingState.value.syllabi = true;
        processingState.value.schedules = true;
        
        errorMessage.value = "";
        processStatus.value = "Iniciando configuración secuencial...";

        const token = getGoogleToken();
        const keys = ['cvs', 'syllabi', 'schedules'];
        
        for (const type of keys) {
            processStatus.value = `Procesando carpeta de ${type}...`;
            const result = await configWebhook(folderState.value[type].id, token);
            if (!result.success) {
                throw new Error(`Error vinculando ${type}: ${result.message || 'Desconocido'}`);
            }
        }

        processStatus.value = "✅ Configuración guardada y webhooks activos.";
        
        // Guardar exitosos en localStorage
        const syncedData = {
          cvs: folderState.value.cvs.id,
          syllabi: folderState.value.syllabi.id,
          schedules: folderState.value.schedules.id
        };
        localStorage.setItem('teacher_ideal_synced_folders', JSON.stringify(syncedData));
        isSynced.value = true;

        setTimeout(() => {
          router.push('/ciclos');
        }, 1500);
        
      } catch (error) {
        console.error("Error procesando archivos:", error);
        errorMessage.value = error.message;
        processStatus.value = "";
      } finally {
        processingState.value.cvs = false;
        processingState.value.syllabi = false;
        processingState.value.schedules = false;
      }
    };

    return {
      userEmail,
      folderState,
      folderList,
      allFoldersSelected,
      processingState,
      webhookActive,
      isAnyProcessing,
      processStatus,
      errorMessage,
      goBack,
      logout,
      selectFolderHandler,
      processData,
      isSynced
    };
  },
};
</script>