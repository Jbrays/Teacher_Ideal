<template>
  <div class="min-h-screen bg-gray-100">

    <header class="w-full bg-white shadow-sm py-4 px-6 flex items-center justify-between">
      <button
        @click="goBack"
        class="text-gray-600 text-lg hover:text-indigo-500 transition"
      >
        ← Atrás
      </button>

      <h1 class="text-xl font-semibold text-gray-800">
        Configuración
      </h1>

      <div></div> </header>

    <div class="max-w-3xl mx-auto px-6 py-10">

      <div class="bg-white shadow rounded-2xl p-6 mb-8">
        <h2 class="text-lg font-semibold text-gray-800 mb-4">Usuario</h2>

        <p class="text-gray-700 font-medium">
          {{ userEmail }}
        </p>

        <button
          @click="logout"
          class="mt-4 w-full bg-red-500 hover:bg-red-600 text-white py-2 rounded-lg font-semibold shadow transition"
        >
          Cerrar sesión
        </button>
      </div>

      <div class="bg-white shadow rounded-2xl p-6 mb-8">
        <h2 class="text-lg font-semibold text-gray-800 mb-4">Carpetas de Google Drive</h2>

        <p class="text-gray-500 mb-6 text-sm">
          Selecciona las carpetas correspondientes para procesar los archivos.
          <strong>Todas son obligatorias.</strong>
        </p>

        <div v-for="folder in folderList" :key="folder.key" class="mb-5">
          <label class="block font-semibold text-gray-700 mb-1">
            {{ folder.icon }} {{ folder.label }}
            <span v-if="folder.optional" class="text-gray-400 text-xs font-normal">(opcional)</span>
          </label>

          <button
            @click="selectFolderHandler(folder.key)"
            class="w-full bg-indigo-600 hover:bg-indigo-700 text-white py-2 rounded-xl font-semibold shadow transition"
          >
            Seleccionar carpeta
          </button>

          <p v-if="folderState[folder.key]?.id" class="text-sm font-medium text-green-700 mt-2 mb-1">
            Carpeta vinculada: "{{ folderState[folder.key].name }}"
          </p>

          <div class="flex flex-col gap-2 mt-2">
            <button
              v-if="folderState[folder.key]?.id && !webhookActive[folder.key]"
              @click="processIndividual(folder.key)"
              :disabled="processingState[folder.key]"
              class="w-full bg-indigo-100 hover:bg-indigo-200 text-indigo-700 py-2 rounded-xl font-medium shadow-sm transition flex items-center justify-center gap-2"
            >
              <span v-if="processingState[folder.key]" class="animate-spin">⏳</span>
              {{ processingState[folder.key] ? 'Vinculando...' : 'Sincronizar y Vincular' }}
            </button>
            <div v-else-if="webhookActive[folder.key]" class="w-full flex items-center justify-center py-2 bg-green-50 text-green-700 rounded-xl font-medium border border-green-200">
              ✅ Webhook Activo
            </div>
          </div>
        </div>

        <div class="border-t border-gray-200 my-6"></div>

        <button
          :disabled="!allFoldersSelected || isAnyProcessing"
          @click="processData"
          class="w-full bg-gray-800 hover:bg-gray-900 text-white py-3 rounded-xl font-semibold shadow transition"
        >
          {{ isAnyProcessing ? 'Sincronizando...' : 'Guardar Configuración y Sincronizar Todo' }}
        </button>

        <p v-if="processStatus" class="text-gray-500 text-sm mt-3 whitespace-pre-line">
          {{ processStatus }}
        </p>

        <p v-if="errorMessage" class="text-red-500 text-sm mt-3">
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

    const processIndividual = async (type) => {
      if (!folderState.value[type]?.id) {
        errorMessage.value = `Selecciona la carpeta de ${type} primero.`;
        return;
      }

      try {
        processingState.value[type] = true;
        errorMessage.value = "";
        processStatus.value = `Vinculando ${type}...`;
        
        const token = getGoogleToken();
        const result = await configWebhook(folderState.value[type].id, token);
        
        if (result.success) {
          webhookActive.value[type] = true;
          processStatus.value = `✅ ${type}: ${result.message}`;
        }
      } catch (error) {
        console.error(`Error procesando ${type}:`, error);
        errorMessage.value = error.message;
        processStatus.value = "";
      } finally {
        processingState.value[type] = false;
      }
    };

    const processData = async () => {
      if (!allFoldersSelected.value) {
        errorMessage.value = "Selecciona todas las carpetas primero";
        return;
      }

      try {
        // Activar todos los estados de carga visualmente
        processingState.value.cvs = true;
        processingState.value.syllabi = true;
        processingState.value.schedules = true;
        
        errorMessage.value = "";
        processStatus.value = "Sincronizando TODO...";

        const result = await processAllData(folderState.value);

        if (result.success) {
          processStatus.value = "✅ Configuración guardada y webhooks activos.";
          webhookActive.value.cvs = true;
          webhookActive.value.syllabi = true;
          webhookActive.value.schedules = true;

          setTimeout(() => {
            router.push('/ciclos');
          }, 1500);
        }
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
      processIndividual
    };
  },
};
</script>